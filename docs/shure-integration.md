# Shure System API Integration

django-micboard connects to Shure System API over authenticated HTTPS. It can synchronize
discovery IPs, poll device state, and subscribe to manufacturer WebSocket updates.

## Requirements

- A supported Shure System API deployment reachable from the Django/Huey hosts
- The System API shared key
- An HTTPS certificate trusted by the host operating system or an internal CA bundle
- The `standard` extra for native Huey support and the `shure` extra for WebSocket telemetry

```bash
uv add "django-micboard[standard,shure]"
```

## Django configuration

The package reads `MICBOARD_CONFIG` from Django settings. It does not read environment variables
directly; the host settings module must map any environment values into this dictionary.

```python
import os

MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get(
        "MICBOARD_SHURE_API_BASE_URL", "https://shure-system.example.com:10000"
    ),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    "SHURE_API_TIMEOUT": 10,
    "SHURE_API_MAX_RETRIES": 3,
}
```

The client sends the shared key in the `x-api-key` header. Set `SHURE_API_USE_DIGEST` to `True`
inside `MICBOARD_CONFIG` only when the System API deployment also requires HTTP Digest auth.

Authenticated endpoints must use HTTPS. Certificate verification cannot be disabled. For an
internal CA, set `SSL_CERT_FILE` or `SSL_CERT_DIR` in both the Django and Huey process
environments.

## Native Huey

Queued polling uses Huey's Django integration from the `huey` package:

```python
import os

INSTALLED_APPS += ["huey.contrib.djhuey"]

HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "micboard",
    "connection": {
        "url": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
    },
    "immediate": os.environ.get("DJANGO_DEBUG", "False").lower() == "true",
}
```

Run a worker outside immediate/development mode:

```bash
uv run --no-sync python manage.py run_huey
```

## Discovery

Create an active `Manufacturer` with code `shure`, then record device IPs through the admin or
management command:

```bash
uv run --no-sync python manage.py discovery_add_devices \
  --manufacturer shure \
  --ips 192.168.1.100,192.168.1.101
```

To push the configured discovery inventory to System API and pull results back:

```bash
uv run --no-sync python manage.py sync_discovery --manufacturer shure
```

`--scan-cidrs` and `--scan-fqdns` expand CIDR/FQDN entries already stored in the discovery
configuration. Use `--max-hosts` to bound each CIDR expansion.

Review candidates at `/admin/micboard/discovereddevice/` before approving them into inventory.

## Polling and connection status

Run one poll synchronously:

```bash
uv run --no-sync python manage.py poll_devices --manufacturer shure
```

Enqueue the same work through native Huey:

```bash
uv run --no-sync python manage.py poll_devices --manufacturer shure --async
```

Inspect persisted real-time connection state:

```bash
uv run --no-sync python manage.py realtime_status --manufacturer shure --verbose
```

Run the Shure diagnostic command when validating a new endpoint:

```bash
uv run --no-sync python manage.py diagnostic_api_health_check
```

## Direct client use

Use the client as a context manager so its `httpx` connection pool closes promptly:

```python
from micboard.integrations.shure.client import ShureSystemAPIClient

with ShureSystemAPIClient() as client:
    devices = client.devices.get_devices()
    discovery_ips = client.discovery.get_discovery_ips()
```

Pass an explicit base URL and shared key when testing a persisted API-server row. Avoid changing
global Django settings for per-server checks:

```python
with ShureSystemAPIClient(
    base_url=server.base_url,
    shared_key=server.shared_key,
) as client:
    health = client.check_health()
```

## Failure handling

The shared HTTP client retries configured transient statuses, honors integer `Retry-After`
headers, and opens its circuit breaker after repeated failures. Relevant `MICBOARD_CONFIG` keys
include:

- `SHURE_API_TIMEOUT`
- `SHURE_API_MAX_RETRIES`
- `SHURE_API_RETRY_BACKOFF`
- `SHURE_API_RETRY_STATUS_CODES`
- `SHURE_API_CIRCUIT_FAILURE_THRESHOLD`
- `SHURE_API_CIRCUIT_RECOVERY_TIMEOUT`

## Troubleshooting

### Authentication failures

- Confirm `MICBOARD_CONFIG["SHURE_API_SHARED_KEY"]` resolves to a non-empty value.
- Confirm the key belongs to the configured System API endpoint.
- Do not log, display, or commit the key.

### Certificate failures

- Keep the `https://` URL; cleartext manufacturer endpoints are rejected.
- Install the issuing CA or configure `SSL_CERT_FILE`/`SSL_CERT_DIR`.
- Restart both Django and Huey after changing process environment variables.

### No discovery results

- Confirm the `shure` manufacturer is active.
- Confirm candidate IPs exist in `/admin/micboard/discovereddevice/`.
- Run `sync_discovery` without scan flags first, then inspect command output and logs.
- Check routing and firewall access from the application host to System API.

### Queued poll does not run

- Confirm `huey.contrib.djhuey` is installed and in `INSTALLED_APPS`.
- Confirm `settings.HUEY` is a dictionary.
- Confirm the Huey consumer is running and can reach its Redis backend.
- Run the synchronous polling command to separate queue problems from API problems.

## Security checklist

- Restrict System API access at the network layer.
- Store shared keys in a secret manager.
- Allow only known Manufacturer API Server hostnames through
  `MICBOARD_API_SERVER_ALLOWED_HOSTS`.
- Use trusted TLS certificates and rotate credentials according to local policy.
- Keep Django admin permissions and tenant boundaries narrow.
