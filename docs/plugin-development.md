# Manufacturer plugin development

This guide describes the plugin boundary that exists in the current codebase. Use it when adding
a manufacturer under `micboard/integrations/<vendor>/`.

!!! note "Implemented architecture"
    [ADR-004](adr/004-standardize-manufacturer-plugins.md) keeps shared transport and plugin
    contracts in `micboard/services/common/base/` while protocol-specific code remains under
    `micboard/integrations/<vendor>/`. `PluginRegistry` loads those integrations by convention;
    there is no central registration module.

## Runtime boundaries

| Concern | Current entry point |
| --- | --- |
| Plugin contract and dynamic import | `micboard.services.common.base.plugin` |
| Cached class lookup and instance construction | `micboard.services.manufacturer.plugin_registry.PluginRegistry` |
| Shared verified HTTP transport | `micboard.services.common.base.client.BaseHTTPClient` |
| API exceptions | `micboard.exceptions` |
| Rate limiting | `micboard.services.common.base.rate_limiter.rate_limit` |
| IPv4 discovery validation | `micboard.services.common.base.utils.validate_ipv4_list` |
| Poll and persistence orchestration | `micboard.services.manufacturer.sync.ManufacturerSyncService` |
| Discovery reconciliation | `micboard.services.sync.discovery_service.DiscoveryService` |
| Native Huey registration | `micboard.apps.MicboardConfig._register_background_tasks` |

The plugin owns manufacturer protocol details. Domain services own persistence, deduplication,
tenant scope, lifecycle transitions, and orchestration. Keep model writes and business decisions out
of integration clients and transformers. The live plugin methods exchange dictionaries; new
service-layer APIs built around them should use typed Pydantic v2 DTOs at the service boundary.

## Plugin contract

`BasePlugin` defines only `name`, `code`, and `get_devices()`. Runtime services require the fuller
`ManufacturerPlugin` contract, which inherits from `BasePlugin`. A new integration should therefore
subclass `ManufacturerPlugin`, not `BasePlugin` directly.

The required methods are:

| Member | Contract |
| --- | --- |
| `name` | Human-readable manufacturer name. |
| `code` | Stable lower-snake-case identifier matching the integration directory and DB row. |
| `get_devices()` | Return raw device mappings; return an empty list when the API has no devices. |
| `get_device(device_id)` | Return one raw device mapping or `None`. |
| `get_device_channels(device_id)` | Return raw channel mappings or an empty list. |
| `get_client()` | Return the configured `BaseAPIClient` implementation. |
| `transform_device_data(api_data)` | Normalize a raw device mapping or return `None` when unusable. |
| `is_healthy()` | Return current client health. |
| `check_health()` | Return the shared health-response mapping. |
| `add_discovery_ips(ips)` | Add validated manual-discovery addresses; report success. |
| `get_discovery_ips()` | Return the current manual-discovery address list. |
| `remove_discovery_ips(ips)` | Remove validated manual-discovery addresses; report success. |

`connect_and_subscribe()` and `transform_transmitter_data()` are not abstract members today. Add
them when the integration supports streaming telemetry or transmitter/channel persistence, because
those runtime paths call them when enabled.

## Create the integration

Use a lower-snake-case vendor code. This example uses `acme_audio`:

```text
micboard/integrations/acme_audio/
├── client.py
├── device_client.py
├── discovery_client.py
├── exceptions.py
├── plugin.py
├── transformers.py
└── stream.py             # optional: SSE or manufacturer WebSocket transport
```

The current integration tree is a namespace package, so no package-level re-export is required.
Import implementations from their defining modules; do not add compatibility aliases.

### 1. Define API exceptions

Use the common exception hierarchy so retry and health behavior remains consistent:

```python
from micboard.exceptions import APIError, APIRateLimitError


class AcmeAudioAPIError(APIError):
    """Acme Audio API request failed."""


class AcmeAudioAPIRateLimitError(AcmeAudioAPIError, APIRateLimitError):
    """Acme Audio API rate limit was exceeded."""
```

Keep response objects and credentials out of exception messages that may reach logs or admin
status fields.

### 2. Build the system client

Subclass `BaseHTTPClient`. It already provides:

- a pooled `httpx.Client`;
- HTTPS URL validation;
- default certificate verification;
- bounded retries and `Retry-After` handling;
- circuit-breaker and health state;
- context-manager cleanup.

Implement only vendor configuration, authentication, health endpoint, and exception types. Compose
device and discovery sub-clients instead of putting every endpoint in `client.py`:

```python
from typing import Any

from micboard.services.common.base.client import BaseHTTPClient

from .device_client import AcmeAudioDeviceClient
from .discovery_client import AcmeAudioDiscoveryClient
from .exceptions import AcmeAudioAPIError, AcmeAudioAPIRateLimitError


class AcmeAudioSystemAPIClient(BaseHTTPClient):
    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(base_url)
        self.devices = AcmeAudioDeviceClient(self)
        self.discovery = AcmeAudioDiscoveryClient(self)

    def _get_config_prefix(self) -> str:
        return "ACME_AUDIO_API"

    def _get_default_base_url(self) -> str:
        return "https://localhost"

    def _configure_authentication(self, config: dict[str, Any]) -> None:
        token = config.get("ACME_AUDIO_API_TOKEN")
        if not isinstance(token, str) or not token:
            raise ValueError("ACME_AUDIO_API_TOKEN is required")
        self.client.headers["Authorization"] = f"Bearer {token}"

    def _get_health_check_endpoint(self) -> str:
        return "/api/health"

    def get_exception_class(self) -> type[AcmeAudioAPIError]:
        return AcmeAudioAPIError

    def get_rate_limit_exception_class(self) -> type[AcmeAudioAPIRateLimitError]:
        return AcmeAudioAPIRateLimitError
```

`BaseHTTPClient` resolves `<PREFIX>_BASE_URL`, `<PREFIX>_TIMEOUT`, retry, and circuit-breaker keys
from the app settings service. Add deployment values through `MICBOARD_CONFIG`, sourcing secrets
from the environment. Never hard-code credentials.

The shared client currently applies its configured retry statuses to every HTTP method. Use that
path for a mutation only when the vendor documents replay safety or supports an idempotency key.
Otherwise, give the vendor mutation an explicit non-retrying request path or disable retries for
that client.

Call `close()` or use `with AcmeAudioSystemAPIClient() as client:` for short-lived direct clients.
Long-lived stream transports should own and close their async client explicitly.

### 3. Add endpoint sub-clients

Sub-clients receive the parent through the narrow `BaseAPIClient` interface and call its shared
`_make_request()` method:

```python
from typing import Any, cast

from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.rate_limiter import rate_limit


class AcmeAudioDeviceClient:
    def __init__(self, api_client: BaseAPIClient) -> None:
        self.api_client = api_client

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> list[dict[str, Any]]:
        result = self.api_client._make_request("GET", "/api/devices")
        return cast(list[dict[str, Any]], result) if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        result = self.api_client._make_request("GET", f"/api/devices/{device_id}")
        return cast(dict[str, Any], result) if isinstance(result, dict) else None

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        result = self.api_client._make_request("GET", f"/api/devices/{device_id}/channels")
        return cast(list[dict[str, Any]], result) if isinstance(result, list) else []
```

Validate response shape at the integration boundary. Return the plugin contract's empty value for
a successful empty response; let the vendor-specific API exception represent a failed request.

### 4. Implement discovery

`DiscoveryService` reconciles desired addresses and invokes the plugin in batches. The integration
is responsible only for translating that list into vendor API calls.

```python
from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.utils import validate_ipv4_list


class AcmeAudioDiscoveryClient:
    def __init__(self, api_client: BaseAPIClient) -> None:
        self.api_client = api_client

    def get_discovery_ips(self) -> list[str]:
        result = self.api_client._make_request("GET", "/api/discovery/ips")
        if not isinstance(result, dict):
            return []
        ips = result.get("ips", [])
        return [ip for ip in ips if isinstance(ip, str)] if isinstance(ips, list) else []

    def add_discovery_ips(self, ips: list[str]) -> bool:
        valid_ips = validate_ipv4_list(ips, "acme_audio.add_discovery_ips")
        if not valid_ips:
            return False
        self.api_client._make_request("PUT", "/api/discovery/ips", json={"ips": valid_ips})
        return True

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        valid_ips = validate_ipv4_list(ips, "acme_audio.remove_discovery_ips")
        if not valid_ips:
            return False
        self.api_client._make_request("DELETE", "/api/discovery/ips", json={"ips": valid_ips})
        return True
```

Preserve the vendor API's existing discovery state when its API uses replace semantics. The Shure
implementation reads, merges, and deduplicates before `PUT`; copy that behavior only when the new
vendor has the same semantics. A vendor without a manual discovery list must still implement the
abstract methods safely (`[]` for reads and `False` for mutations) and must not pretend a remote
mutation succeeded.

Do not perform local ownership checks here. Cross-manufacturer IP ownership belongs to
`DiscoveryService` and its persistence services.

### 5. Normalize vendor payloads

Transformers are pure protocol adapters: raw vendor mapping in, normalized mapping or `None` out.
They must not query or write Django models.

`NormalizedHardware.from_api()` is the current persistence boundary. At minimum, a usable device
needs a non-empty `id` (or `api_device_id`) and `ip`. Return stable values for these recommended
keys when the vendor supplies them:

```python
from typing import Any


class AcmeAudioDataTransformer:
    @staticmethod
    def transform_device_data(api_data: dict[str, Any]) -> dict[str, Any] | None:
        device_id = api_data.get("deviceId")
        ip_address = api_data.get("address")
        if not isinstance(device_id, str) or not device_id:
            return None
        if not isinstance(ip_address, str) or not ip_address:
            return None

        return {
            "id": device_id,
            "ip": ip_address,
            "name": str(api_data.get("name") or ""),
            "model": str(api_data.get("model") or ""),
            "device_type": str(api_data.get("deviceType") or ""),
            "serial_number": str(api_data.get("serialNumber") or ""),
            "mac_address": str(api_data.get("macAddress") or ""),
            "firmware_version": str(api_data.get("firmwareVersion") or ""),
            "channels": api_data.get("channels", []),
        }
```

When channel polling is supported, `get_device_channels()` should return mappings shaped like
`{"channel": 1, "tx": {...}}`. Add `transform_transmitter_data(tx_data, channel_num)` to the
plugin and return the fields consumed by hardware polling, such as `slot`, `name`, `battery`,
`battery_charge`, `runtime`, `audio_level`, `rf_level`, `frequency`, `antenna`, and `status`.

Test missing IDs, missing addresses, unknown models, empty channel lists, malformed scalar types,
and representative real payload fixtures. Avoid catching broad exceptions merely to manufacture
partially valid hardware identities.

### 6. Implement the plugin

The plugin should remain a thin delegate:

```python
from typing import Any

from micboard.services.common.base.plugin import ManufacturerPlugin

from .client import AcmeAudioSystemAPIClient
from .transformers import AcmeAudioDataTransformer


class AcmeAudioPlugin(ManufacturerPlugin):
    def __init__(self, manufacturer: Any | None = None) -> None:
        super().__init__(manufacturer)
        self._client: AcmeAudioSystemAPIClient | None = None
        self.transformer = AcmeAudioDataTransformer()

    @property
    def name(self) -> str:
        return "Acme Audio"

    @property
    def code(self) -> str:
        return "acme_audio"

    def get_client(self) -> AcmeAudioSystemAPIClient:
        if self._client is None:
            self._client = AcmeAudioSystemAPIClient()
        return self._client

    def get_devices(self) -> list[dict[str, Any]]:
        return self.get_client().devices.get_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        return self.get_client().devices.get_device(device_id)

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        return self.get_client().devices.get_device_channels(device_id)

    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        return self.transformer.transform_device_data(api_data)

    def is_healthy(self) -> bool:
        return self.get_client().is_healthy()

    def check_health(self) -> dict[str, Any]:
        return self.get_client().check_health()

    def get_discovery_ips(self) -> list[str]:
        return self.get_client().discovery.get_discovery_ips()

    def add_discovery_ips(self, ips: list[str]) -> bool:
        return self.get_client().discovery.add_discovery_ips(ips)

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        return self.get_client().discovery.remove_discovery_ips(ips)
```

If a plugin holds a client for its lifetime, the caller that owns that plugin also owns cleanup.
Do not create a new client for every endpoint call.

### 7. Register and activate the plugin

Registration is convention-based; there is no central plugin map to edit.

For code `acme_audio`, the loader imports `micboard.integrations.acme_audio.plugin` and first looks
for `AcmeAudioPlugin`. If that exact class name is absent, it falls back to another
`ManufacturerPlugin` subclass in the module. Prefer the exact name and keep the class concrete so
discovery is deterministic.

Verify class loading:

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

plugin_class = PluginRegistry.get_plugin_class("acme_audio")
assert plugin_class.__name__ == "AcmeAudioPlugin"
```

Create or enable a `micboard.models.discovery.manufacturer.Manufacturer` row whose `code` is exactly
`acme_audio`. `PluginRegistry.get_plugin()` can then instantiate the class with that row, and
`get_all_active_plugins()` includes it when `is_active=True`.

`PluginRegistry` caches plugin classes. Call `PluginRegistry.clear_cache()` only in tests or an
explicit development reload path. Do not add package re-exports or a compatibility registration
module.

`ManufacturerConfiguration` validation and the admin API-server connection checker have explicit
vendor behavior. Extend those separate surfaces only if the new integration uses them; do not
describe them as automatic consequences of plugin registration.

## Protocol-specific patterns

Streaming is optional and is not part of `ManufacturerPlugin`'s abstract contract.

### REST polling

Use the shared `BaseHTTPClient`, device/discovery sub-clients, and generic poll/discovery services.
No streaming method is needed. Keep network requests outside DB transactions; pass normalized data
to services for persistence.

### Server-Sent Events

Place stream parsing in a vendor module such as `sse_client.py` or `stream.py`. Use
`httpx.AsyncClient` without overriding certificate verification, set a finite connect/write/pool
timeout, and allow an unbounded read timeout only for the event stream. Parse only `data:` records,
validate JSON, and await an async callback.

The generic SSE task path awaits `plugin.connect_and_subscribe(device_id, callback)`, so a new SSE
plugin should expose an async method with that shape. Do not treat the existing vendor-specific
bridge as a base-class API.

### Manufacturer WebSocket

Use an async `connect_and_subscribe()` method and a vendor transport module. Require an absolute
`wss://` URL, rely on the WebSocket library's certificate-verification defaults, validate the
handshake, and redact transport IDs, device IDs, URLs containing credentials, and payload secrets
from logs.

The Shure WebSocket path and `start_shure_websocket_subscriptions()` task are Shure-specific. A new
WebSocket vendor needs its own service boundary and thin task wrapper; it must not import or branch
inside Shure code.

Manufacturer WebSockets are backend-to-hardware transports. They are separate from the browser
Channels endpoint at `/ws` documented in the [WebSocket API](api/websocket.md).

If a protocol needs an additional package, add it to the appropriate optional dependency extra in
`pyproject.toml` and refresh `uv.lock` with `uv lock`. Keep imports optional so REST-only hosts do
not need streaming dependencies.

## Native Huey boundary

Generic polling and discovery task functions are already registered by
`MicboardConfig._register_background_tasks()`. A plugin using only those paths needs no queue code.

For new protocol-specific background work:

1. Put business and protocol orchestration in a service.
2. Add a thin, typed function under `micboard/tasks/<domain>/` that accepts serializable IDs, not
   model instances or live clients.
3. Add that function to `MicboardConfig._register_background_tasks()`.
4. Enqueue it through `enqueue_huey_task()`; registration uses native Huey's `on_commit_task`, so
   submission waits for a successful commit on Django's default DB connection. The current wrapper
   does not select a non-default DB alias.
5. Test with the configured `MemoryHuey` backend and verify rollback/on-commit behavior.

Do not add another task queue or hold DB transactions open during network I/O. Long-lived SSE or
WebSocket subscriptions consume worker capacity; schedule and isolate them deliberately in the
host deployment.

## Security requirements

- Require absolute HTTPS API URLs and WSS manufacturer-stream URLs.
- Keep `httpx` and WebSocket certificate verification enabled. For private CAs, configure
  `SSL_CERT_FILE` or `SSL_CERT_DIR`; never add a `verify=False` escape hatch.
- Source credentials from deployment secrets and pass only the credential belonging to the target
  server. Never fall back from a row-scoped credential to another server's global credential.
- Never log tokens, passwords, authorization headers, subscription IDs, full private payloads, or
  credential-bearing URLs.
- Validate response types, address lists, bounded identifiers, and retry semantics at the
  integration edge.
- Do not retry non-idempotent mutations unless the vendor API documents safe replay behavior.
- If admin-managed API server rows initiate outbound connections, preserve
  `MICBOARD_API_SERVER_ALLOWED_HOSTS` validation in `APIServerConnectionService`; plugin loading
  alone does not grant an endpoint permission.
- Keep tenant filtering and model permissions in services/admin boundaries. A plugin must never
  widen a caller-scoped queryset.

## Testing a plugin

Build coverage at each boundary without contacting real hardware:

1. **Contract:** assert `issubclass(AcmeAudioPlugin, ManufacturerPlugin)` and
   `not AcmeAudioPlugin.__abstractmethods__`.
2. **Registry:** verify the exact code loads the exact class, class lookup is cached, and an unknown
   code fails as documented. Clear the registry cache around tests.
3. **Transport:** use `httpx.MockTransport` or mocks to cover auth, endpoint paths, response shapes,
   retryable statuses, rate limits, timeouts, invalid JSON, and client cleanup.
4. **TLS and secrets:** reject HTTP/WS, assert no verification override is passed, and use `caplog`
   to prove credentials and private handshake values are absent.
5. **Discovery:** test invalid addresses, empty inputs, deduplication/replace semantics, remote read
   failures, and unsuccessful mutations.
6. **Transformers:** use representative vendor fixtures plus missing/unknown/malformed payloads;
   assert stable normalized IDs and addresses.
7. **Service integration:** mock only the transport, then exercise `ManufacturerSyncService` and
   `DiscoveryService` with the DB to cover deduplication, ownership, persistence, and failure
   containment.
8. **Streaming:** use fake async iterators/connections; cover handshake failure, malformed events,
   callback errors, normal close, and secret-safe logging.
9. **Huey:** test the plain task function and native-Huey enqueue/on-commit behavior separately.

Existing examples live in `tests/test_plugin_registry.py`, `tests/test_httpx_clients.py`,
`tests/test_authenticated_transport_security.py`, `tests/services/sync/`, and
`tests/test_huey_integration.py`.

Run focused and repository gates through the locked uv environment:

```bash
uv run --no-sync pytest tests/ -k "acme_audio" -v
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync python -m mypy micboard
uv run --no-sync bandit -r micboard -ll
uv run --no-sync mkdocs build --strict
```

## New integration checklist

- [ ] Vendor code is stable, lower-snake-case, and matches directory, plugin property, and
      `Manufacturer.code`.
- [ ] Plugin subclasses `ManufacturerPlugin` and has no unimplemented abstract methods.
- [ ] System client subclasses `BaseHTTPClient`; endpoint sub-clients use `BaseAPIClient`.
- [ ] API and stream URLs require TLS with certificate verification enabled.
- [ ] Authentication fails closed; secrets never appear in source, exceptions, or logs.
- [ ] Device and channel response shapes are validated at the integration boundary.
- [ ] Transformer returns stable normalized identity/address fields and performs no DB work.
- [ ] Discovery methods validate addresses and honor vendor merge/replace semantics.
- [ ] REST, SSE, or WebSocket behavior follows the matching async/sync caller contract.
- [ ] Persistence, tenant scope, deduplication, and lifecycle behavior remain in services.
- [ ] Any new task is a thin native-Huey wrapper registered by `MicboardConfig`.
- [ ] Any new optional dependency is scoped to an existing/relevant extra and locked with `uv`.
- [ ] Registry, transport, transformer, discovery, security, service, and streaming tests pass.
- [ ] `PluginRegistry.get_plugin_class("<vendor>")` resolves the intended class.
- [ ] An active `Manufacturer` row exists with the exact plugin code.
- [ ] Developer docs and `CHANGELOG.md` describe the supported integration behavior.
