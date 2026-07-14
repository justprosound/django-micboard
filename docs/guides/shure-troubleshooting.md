# Shure troubleshooting

Use these checks to separate configuration, transport, discovery, polling, and queue failures.
Run project commands through the locked uv environment.

## 1. Verify Django configuration

Shure values belong in `MICBOARD_CONFIG`; `MICBOARD_SHURE_API` is not a supported Django
setting.

```python
import os

MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get(
        "MICBOARD_SHURE_API_BASE_URL", "https://shure-system.example.com:10000"
    ),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
}
```

The package does not read environment variables directly. Verify the host settings module maps
them and that Django starts cleanly:

```bash
uv run --no-sync python manage.py check
uv run --no-sync python manage.py shell -c \
  'from micboard.services.settings.settings_service import settings; print(settings.get("SHURE_API_BASE_URL")); print(bool(settings.get("SHURE_API_SHARED_KEY")))'
```

The second command prints only whether a key exists, never its value.

## 2. Verify HTTPS and trust

Manufacturer clients reject cleartext URLs. If the endpoint uses an internal CA, install that CA
in the host trust store or set `SSL_CERT_FILE`/`SSL_CERT_DIR` for Django and Huey.

```bash
curl --fail --show-error --cacert /path/to/internal-ca.pem \
  https://shure-system.example.com:10000/api/v1/devices
```

An HTTP authentication response still proves DNS, routing, TCP, and TLS are working. Avoid
putting the shared key on a shell command line or in shell history.

## 3. Run the built-in diagnostic

```bash
uv run --no-sync python manage.py diagnostic_api_health_check
```

Common outcomes:

- `SHURE_API_SHARED_KEY not configured`: fix the host settings mapping.
- certificate verification error: install the issuing CA; do not disable verification.
- connection refused or timeout: check endpoint, route, firewall, and System API process.
- HTTP 401/403: confirm the shared key belongs to this endpoint.

## 4. Check discovery inventory

Confirm an active manufacturer with code `shure` exists. Add bounded candidates explicitly:

```bash
uv run --no-sync python manage.py discovery_add_devices \
  --manufacturer shure \
  --ips 192.168.1.100,192.168.1.101
```

Inspect candidates without exposing credentials:

```bash
uv run --no-sync python manage.py shell -c \
  'from micboard.models.discovery.registry import DiscoveredDevice; print(list(DiscoveredDevice.objects.values_list("ip", "status")))'
```

Synchronize existing discovery records first:

```bash
uv run --no-sync python manage.py sync_discovery --manufacturer shure
```

Only use `--scan-cidrs` after configuring CIDRs in admin. Keep `--max-hosts` bounded.

## 5. Separate polling from Huey

Run one synchronous poll:

```bash
uv run --no-sync python manage.py poll_devices --manufacturer shure
```

If it succeeds, test queue dispatch:

```bash
uv run --no-sync python manage.py poll_devices --manufacturer shure --async
```

Queued work requires `huey.contrib.djhuey` in `INSTALLED_APPS`, a dictionary at
`settings.HUEY`, and a running consumer:

```bash
uv run --no-sync python manage.py run_huey
```

## 6. Inspect connection state

```bash
uv run --no-sync python manage.py realtime_status --manufacturer shure --verbose
```

For backend Shure WebSocket subscriptions, install the `shure` extra and confirm the derived
URL is `wss://`. Browser-facing Channels routing is a separate connection path.

## 7. Enable focused logs

Configure the host project's Django logging without creating a file path the service user cannot
write:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "micboard.integrations.shure": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
```

Logs intentionally omit shared-key values. Do not add temporary credential logging.

## Reporting a bug

Include:

- django-micboard, Django, and Python versions
- exact management command and traceback
- endpoint hostname/port with secrets removed
- whether synchronous polling succeeds
- whether the failure occurs in Django, Huey, or both
- relevant redacted logs

```bash
uv run --no-sync python -c \
  'import django, micboard, sys; print(sys.version); print(django.get_version()); print(micboard.__file__)'
uv tree --depth 1
```

Open issues at [GitHub Issues](https://github.com/justprosound/django-micboard/issues).
