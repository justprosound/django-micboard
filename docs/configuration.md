# Micboard Configuration

To use `django-micboard` in your project, you need to configure your project's `settings.py` file.

## INSTALLED_APPS

Add `micboard` and `channels` to your `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = [
    # ... other apps
    "channels",
    "micboard",
]
```

## MICBOARD_CONFIG

`django-micboard` is configured through a single dictionary in your `settings.py` called `MICBOARD_CONFIG`. All keys are optional except where noted. The following keys are available:

| Key | Description | Default |
|-----|-------------|---------|
| `SHURE_API_BASE_URL` | The HTTPS base URL of the Shure System API (required) | `"https://localhost:10000"` |
| `SHURE_API_SHARED_KEY` | The shared secret API key for Shure System API | `None` |
| `SHURE_API_TIMEOUT` | Timeout in seconds for API requests | `10` |
| `SHURE_API_MAX_RETRIES` | Maximum number of retries for failed requests | `3` |
| `SHURE_API_RETRY_BACKOFF` | Backoff factor for retries (seconds) | `0.5` |
| `SHURE_API_RETRY_STATUS_CODES` | HTTP status codes to retry | `[429, 500, 502, 503, 504]` |
| `POLL_INTERVAL` | Interval in seconds between device polls | `5` |
| `CACHE_TIMEOUT` | Timeout in seconds for API response caching | `30` |
| `TRANSMITTER_INACTIVITY_SECONDS` | Seconds before transmitter marked inactive | `10` |

Post-poll alert evaluation uses four top-level Django settings, not `MICBOARD_CONFIG` keys:

| Setting | Bounds | Purpose |
|---------|--------|---------|
| `MICBOARD_POLL_ALERT_MAX_UNITS` | Default: 100; hard maximum: 500 | Wireless units evaluated per manufacturer poll |
| `MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS` | Default: 100; hard maximum: 500 | Active performer assignments evaluated per poll |
| `MICBOARD_POLL_ALERT_MAX_RECIPIENTS` | Default: 250; hard maximum: 1,000 | Active group recipients evaluated per poll |
| `MICBOARD_POLL_ALERT_MAX_DELIVERIES` | Default: 250; hard maximum: 1,000 | Alert persistence attempts allowed per poll |

Micboard rotates shared-cache cursors through bounded pages so later units, assignments, and
recipients are not permanently starved. It filters inactive assignments, monitoring groups, and
users before fanout, then revalidates the recipient, assignment, group, and tenant scope before
alert persistence and again before email delivery. A cache outage falls back to the first bounded
page without disabling alert evaluation. Hardware-offline and transmitter checks alternate which
runs first on each poll so one alert scope cannot consume every budget. The wireless-unit cursor
advances after every attempted unit, including when fanout truncation ends a page early.

Manufacturer inventory synchronization is bounded by the top-level
`MICBOARD_POLL_MAX_DEVICES` setting (default: 500, hard maximum: 5,000). Micboard samples at most
one item beyond the configured limit to detect overflow. An oversized response fails closed before
any part of that inventory is persisted. Polling and discovery realtime projections also send at
most this many devices per invocation and resume later rows from a shared-cache cursor. Each batch
is emitted in bounded chunks; `MICBOARD_POLL_BROADCAST_CHUNK_SIZE` controls their size (default:
100, hard maximum: 500). Configure a process-shared cache to preserve broadcast fairness across
workers.

Vendor HTTP and SSE consumption uses top-level Django settings with immutable package ceilings:

| Setting | Default | Hard maximum | Purpose |
|---------|---------|--------------|---------|
| `MICBOARD_HTTP_MAX_RETRY_DELAY_SECONDS` | 30 seconds | 300 seconds | Caps both exponential retry backoff and numeric `Retry-After` delays |
| `MICBOARD_HTTP_MAX_RESPONSE_BYTES` | 2 MiB | 16 MiB | Caps decoded successful response bytes before JSON parsing |
| `MICBOARD_SSE_MAX_LINE_BYTES` | 64 KiB | 1 MiB | Caps each decoded SSE line retained by the stream parser |
| `MICBOARD_SSE_MAX_EVENT_BYTES` | 64 KiB | 1 MiB | Caps JSON data retained and parsed from one SSE event line |

Invalid or nonpositive values use the defaults; values above a hard maximum are clamped. HTTP and
SSE bodies are consumed in decoded 8 KiB chunks, so compressed, chunked, and newline-free vendor
responses cannot bypass the retained-byte limits. Oversized HTTP responses fail before JSON
decoding, while oversized SSE lines or events are discarded without logging their contents.

Discovery reconciliation bounds each candidate projection at a hard 4,096 items. Shared-cache
cursors rotate local inventory pages and fairly allocate configured definition pages between CIDR
and FQDN sources. These cursors use Django's default cache; configure that cache as process-shared
when multiple workers run discovery. An incomplete source page, lookup, or address expansion may
contribute its valid bounded results, but it is not treated as authoritative for removals: Micboard
retains remote entries except database-proven cross-manufacturer conflicts. A single CIDR larger
than the per-run address budget remains bounded and incomplete; split large ranges into smaller
CIDRs that fit the intended scan budget when full address-space coverage is required.

Charger snapshot polling uses three top-level Django settings. `MICBOARD_CHARGER_MAX_DEVICES`
(default: 100, hard maximum: 500) bounds inventory processing,
`MICBOARD_CHARGER_MAX_STATIONS` (default: 64, hard maximum: 256) bounds unique station API calls,
and `MICBOARD_CHARGER_MAX_SLOTS` (default: 32, hard maximum: 128) bounds slots read per station.
These are not `MICBOARD_CONFIG` keys. Queued polls revalidate that the manufacturer remains active.
List-like vendor inventories resume from a cached offset over multiple polls, and the public
dashboard snapshot changes only after a complete inventory cycle. Truncated one-shot iterables
retain the previous complete snapshot because they cannot resume safely. The station cap retains a
deterministic vendor-order prefix across cycles instead of rotating partial snapshots. Deployments
whose inventories exceed one page, especially multi-worker deployments, must use a process-shared
default cache to preserve continuation state.

The package reads this Django dictionary; it does not read process environment variables
directly. Map secrets from the host's environment or secret manager in the settings module.

## Manufacturer API server allowlist

Admin connection checks for persisted Manufacturer API Server rows require an exact hostname
allowlist outside `MICBOARD_CONFIG`:

```python
MICBOARD_API_SERVER_ALLOWED_HOSTS = [
    "shure-system.example.com",
    "shure-system.internal.example",
]
```

Entries are hostnames only: do not include a scheme, port, path, or wildcard. This prevents an
editable admin URL from sending manufacturer credentials to an arbitrary destination. An empty
allowlist denies all admin connection checks.

## Authentication

The Shure System API requires authentication using a shared secret API key. This key is automatically generated when the Shure System API runs for the first time.

### API Key Authentication (Shared Secret)

Configure the shared secret in your settings:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://my-shure-api.local:10000",
    "SHURE_API_SHARED_KEY": "your-shared-secret-here",
}
```

The shared secret is automatically generated when the Shure System API runs for the first time. On Windows systems, it can be found at:
```
C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt
```

**Note**: The shared secret is required for all API requests to the Shure System API.

## SSL/TLS Configuration

Micboard requires HTTPS for authenticated Shure System API connections. Certificate verification
is mandatory.

### Self-Signed Certificates

Install the issuing certificate authority in the host trust store, or set `SSL_CERT_FILE` to a CA
bundle (or `SSL_CERT_DIR` to a CA directory) before starting Django and Huey. Verification cannot
be disabled through Micboard settings or client arguments.

### Production Recommendations

For production deployments:
- Use valid SSL certificates from a trusted Certificate Authority
- Keep the host CA trust store current
- Consider using mutual TLS authentication if supported by your Shure System API

Example with HTTPS:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://my-shure-api.local:10000",
    "SHURE_API_TIMEOUT": 15,
    "POLL_INTERVAL": 10,
}
```

## Polling Configuration

Configure device polling frequency and behavior:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://my-shure-api.local:10000",
    "POLL_INTERVAL": 10,  # Poll every 10 seconds
    "CACHE_TIMEOUT": 60,  # Cache responses for 60 seconds
    "TRANSMITTER_INACTIVITY_SECONDS": 30,  # Mark transmitters inactive after 30s
}
```

## WebSocket Support (Channels)

For real-time updates, `django-micboard` uses Django Channels. You need to configure an ASGI application and a channel layer.

In your project's `settings.py`:

```python
ASGI_APPLICATION = "your_project.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
        # For production, it is highly recommended to use Redis:
        # "BACKEND": "channels_redis.core.RedisChannelLayer",
        # "CONFIG": {
        #     "hosts": [("127.0.0.1", 6379)],
        # },
    },
}
```

Make sure your project has an `asgi.py` file.

## Caching

The app uses Django's cache framework to cache API responses. You should configure a cache backend in your `settings.py`. For development, the local memory cache is sufficient.

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "micboard-cache",
    }
}
```

For production, consider using a more robust cache backend like Redis or Memcached.

## Logging

The app uses the `micboard` logger. You can configure it in your `LOGGING` setting:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "micboard": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
```

## Management Commands

The app provides several management commands for device management and monitoring:

```bash
# Poll devices from manufacturers
uv run --no-sync python manage.py poll_devices

# Poll one active manufacturer, or explicitly override inactivity for an operator-run poll
uv run --no-sync python manage.py poll_devices --manufacturer shure
uv run --no-sync python manage.py poll_devices --manufacturer shure --force

# Sync discovery results
uv run --no-sync python manage.py sync_discovery

# Add Shure device IPs manually (comma-separated)
uv run --no-sync python manage.py discovery_add_devices --ips 192.168.1.100,192.168.1.101

# Subscribe to real-time status
uv run --no-sync python manage.py realtime_status

# WebSocket subscriptions
uv run --no-sync python manage.py websocket_subscribe

# Server-Sent Events subscription
uv run --no-sync python manage.py sse_subscribe
```

See [API Reference](api/management.md) for detailed command documentation.

### Realtime subscription supervisors

The SSE and WebSocket task entrypoints and management commands share a cache-backed singleton
lease. Production deployments with multiple Huey processes must configure a process-shared Django
cache and may select it with `MICBOARD_REALTIME_CACHE_ALIAS` (default: `"default"`). Local-memory
caches only deduplicate workers inside one process.

The management commands run in the foreground. Queue-managed deployments should explicitly
enqueue the registered native Huey task entrypoint once. Manufacturer polling never starts or
enqueues a realtime supervisor.

`MICBOARD_REALTIME_MAX_DEVICES` (default: 64, hard maximum: 256) bounds each inventory window.
Micboard stores a circular primary-key cursor in the selected shared cache, so later rounds in the
same supervisor—and later restarts—continue through eligible inventory instead of repeatedly
selecting the first rows.
`MICBOARD_REALTIME_MAX_CONCURRENCY` (default: 16, hard maximum: 64) bounds simultaneous device
subscriptions and worker tasks. `MICBOARD_REALTIME_ROTATION_SECONDS` (default: 300, hard maximum:
3,600) limits each long-lived connection's turn before the worker advances to the next selected
device. `MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS` (default: 1, hard maximum: 60) controls the
pause between repeated inventory rounds. A single-device diagnostic selection bypasses the shared
inventory cursor. After each round, a long-lived supervisor reloads the next eligible bounded
window from the database, so inventory and eligibility changes take effect during the same worker
lifetime rather than waiting for a restart.

Queued polling, API-health, discovery, and realtime work revalidates `Manufacturer.is_active`
immediately before outbound vendor access. SSE and WebSocket supervisors also revalidate before
each subscription and inventory reload, ending the live supervisor after deactivation. The
`poll_devices --force` operator override is the only polling exception; it is preserved when the
command enqueues native Huey work. Without `--force`, a specific inactive `--manufacturer` is
rejected just like an inactive manufacturer in an all-manufacturer run.

Leases are renewed while a supervisor runs and expire within 60 seconds after it stops. They are
not explicitly deleted because Django's generic cache API cannot atomically delete only the
current owner's token.
