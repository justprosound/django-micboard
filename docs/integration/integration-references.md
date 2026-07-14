# Manufacturer integration reference

django-micboard currently ships Shure System API and Sennheiser SSCv2 plugins. Both use the
shared `httpx` transport, retry/circuit-breaker behavior, exception hierarchy, and cache-backed
request pacing in `micboard.services.common.base`.

## Clients and authentication

| Manufacturer | Client | Authentication | Required `MICBOARD_CONFIG` keys |
| --- | --- | --- | --- |
| Shure | `ShureSystemAPIClient` | `x-api-key`; optional Digest using the same key | `SHURE_API_BASE_URL`, `SHURE_API_SHARED_KEY` |
| Sennheiser | `SennheiserSystemAPIClient` | HTTP Basic user `api` | `SENNHEISER_API_BASE_URL`, `SENNHEISER_API_PASSWORD` |

Both clients require absolute HTTPS URLs. Trust private certificate authorities with
`SSL_CERT_FILE` or `SSL_CERT_DIR`; certificate verification cannot be disabled.

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://shure-system.example.com:10000",
    "SHURE_API_SHARED_KEY": "loaded-from-a-secret-manager",
    "SENNHEISER_API_BASE_URL": "https://sennheiser-system.example.com",
    "SENNHEISER_API_PASSWORD": "loaded-from-a-secret-manager",
}
```

Do not put real credentials in source control.

## Module map

### Shared transport

- `micboard.services.common.base.client.BaseHTTPClient`: HTTPS validation, connection pooling,
  retries, health checks, and circuit-breaker integration
- `micboard.services.common.base.exceptions`: common API exception types
- `micboard.services.common.base.rate_limiter`: cache-backed minimum request intervals
- `micboard.services.common.base.plugin.ManufacturerPlugin`: plugin interface

### Shure

- `micboard.integrations.shure.client.ShureSystemAPIClient`
- `micboard.integrations.shure.device_client.ShureDeviceClient`
- `micboard.integrations.shure.discovery_client.ShureDiscoveryClient`
- `micboard.integrations.shure.transformers.ShureDataTransformer`
- `micboard.integrations.shure.websocket`: System API WebSocket subscription transport

### Sennheiser

- `micboard.integrations.sennheiser.client.SennheiserSystemAPIClient`
- `micboard.integrations.sennheiser.device_client.SennheiserDeviceClient`
- `micboard.integrations.sennheiser.discovery_client.SennheiserDiscoveryClient`
- `micboard.integrations.sennheiser.transformers.SennheiserDataTransformer`
- `micboard.integrations.sennheiser.sse_client`: SSCv2 server-sent-event transport

## Sennheiser Sound Control Protocol

The Sennheiser plugin targets SSCv2 over HTTPS with HTTP Basic authentication. Its username is
fixed to `api`; `SENNHEISER_API_PASSWORD` supplies the host-configured password. Real-time device
events use the integration's SSE client.

## Plugin loading

`PluginRegistry` resolves a plugin from the persisted manufacturer's code:

```python
from micboard.services.manufacturer.plugin_registry import PluginRegistry

plugin = PluginRegistry.get_plugin(manufacturer.code, manufacturer=manufacturer)
if plugin is None:
    raise RuntimeError(f"No plugin for {manufacturer.code}")

health = plugin.check_health()
```

Add new integrations under `micboard/integrations/<code>/` and implement
`ManufacturerPlugin`. Keep persistence/orchestration in domain services rather than in the
transport client.

## Request behavior

Device and discovery clients apply bounded request rates through the shared decorator. The base
HTTP client also:

- retries configured transient HTTP statuses and transport errors
- honors integer `Retry-After` headers
- raises manufacturer-specific exceptions for HTTP and rate-limit failures
- records successes/failures in its circuit breaker
- exposes `close()` and context-manager support

Prefer context-managed direct client use:

```python
from micboard.integrations.shure.client import ShureSystemAPIClient

with ShureSystemAPIClient() as client:
    devices = client.devices.get_devices()
```

Normal application flows should use plugins and services so tenant scope, persistence, audit,
and broadcasts stay consistent.

## Shared rate limiter

Device/discovery methods use `micboard.services.common.base.rate_limiter.rate_limit`. The
decorator stores each method's last-call time in Django cache and delays calls to preserve the
configured minimum interval. Configure a shared production cache when multiple processes must
coordinate these intervals.

## Validation commands

Integration coverage lives in the root `tests/` tree:

```bash
# Auth, HTTPS enforcement, retry handling, Shure WebSockets, and Sennheiser SSE
uv run --no-sync pytest \
  tests/test_httpx_clients.py \
  tests/test_authenticated_transport_security.py

# Plugin loading and runtime polling paths
uv run --no-sync pytest \
  tests/test_plugin_registry.py \
  tests/test_polling_runtime.py \
  tests/test_polling_api_service.py

# Discovery synchronization
uv run --no-sync pytest tests/test_shure_discovery_sync.py

# All manufacturer-focused tests
uv run --no-sync pytest tests/ -k "shure or sennheiser"
```

## External documentation

- [Shure System API](https://www.shure.com/en-US/products/software/systemapi)
- [Shure API Explorer](https://shure.secure.force.com/apiexplorer)
- [Sennheiser Sound Control Protocol](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html)

## Related guides

- [Shure integration](../shure-integration.md)
- [Shure troubleshooting](../guides/shure-troubleshooting.md)
- [Discovery workflow](discovery-workflow.md)
- [Architecture](../development/architecture.md)
