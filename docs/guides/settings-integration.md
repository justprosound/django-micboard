# Integrating Micboard Settings

Use the canonical `SettingsService` singleton for every runtime read:

```python
from micboard.services.settings.settings_service import settings as micboard_settings
```

## Scoped configurable values

Pass the scope already owned by the workflow. Do not rediscover tenant context inside the settings layer.

```python
poll_interval = micboard_settings.get(
    "polling_interval_seconds",
    300,
    organization=device.organization,
    site=device.site,
    manufacturer=device.manufacturer,
)
```

The most specific stored value wins. If no stored value matches, resolution continues through host `MICBOARD_CONFIG`, package defaults, the registered definition default, and the explicit default.

## Deployment controls

Process safety, transport bounds, and tenancy feature flags use `MICBOARD_*` Django settings:

```python
max_devices = micboard_settings.get("MICBOARD_REALTIME_MAX_DEVICES", 128)
if micboard_settings.msp_enabled:
    ...
```

These values are deliberately host-owned. Database settings cannot override them.

## Typed writes

Views, forms, and commands must delegate writes to `SettingsPersistenceService`. Build the DTO accepted by the service and pass the authenticated actor plus explicit scope. The service validates authorization, definition type, serialized value, and scope before upsert, then invalidates caches.

Never:

- import `SettingsRegistry` from its internal module in runtime code;
- call `Setting.objects.update_or_create(...)` outside the settings persistence service;
- add a wrapper, alias, or re-export for a removed settings API;
- read `settings.MICBOARD_*` or `getattr(settings, "MICBOARD_*", ...)` directly.

## Performance

Resolution is cached per definition and exact scope. Prefer one service read per logical workflow and pass the resolved value down when processing a batch. Database-backed settings should not be loaded in a row loop.

## Testing an integration

Cover:

1. the explicit default;
2. definition and `MICBOARD_CONFIG` fallback;
3. global-to-specific database precedence;
4. isolation from a different organization/site/manufacturer;
5. immutable host precedence for `MICBOARD_*` controls;
6. persistence authorization and automatic cache invalidation.

Run:

```bash
uv run --no-sync pytest tests/test_settings.py tests/test_settings_service.py \
  tests/services/settings tests/test_settings_architecture.py
uv run --no-sync ruff check micboard/services/settings tests/services/settings
uv run --no-sync python -m mypy micboard/services/settings
```

See [Settings Management](settings-management.md) and [ADR-005: Unify Settings Proxy](../adr/005-unify-settings-proxy.md) for the complete contract.