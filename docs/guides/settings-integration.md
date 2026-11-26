---
title: "Read and write settings in code"
description: "Read scoped settings, write them through the persistence service, add a new definition, and test it."
type: how-to
audience: developer
---
Resolution rules and module ownership are in [Settings management](settings-management.md).

## Read a setting

Use the `SettingsService` singleton for every runtime read and pass the scope your workflow already owns:

```python
from micboard.services.settings.settings_service import settings as micboard_settings

poll_interval = micboard_settings.get(
    "polling_interval_seconds",
    300,
    organization=device.organization,
    site=device.site,
    manufacturer=device.manufacturer,
)
```

Deployment controls and feature flags are host-owned:

```python
max_devices = micboard_settings.get("MICBOARD_REALTIME_MAX_DEVICES", 128)
if micboard_settings.msp_enabled:
    ...
```

Prefer one read per workflow and pass the resolved value down when processing a batch. Do not read settings in a row loop.

## Write a setting

Views, forms and commands send a validated DTO to `micboard.services.settings.persistence_service.SettingsPersistenceService` with the acting user and explicit scope. Never import `SettingsRegistry` in runtime code, call `Setting.objects.update_or_create(...)` outside that service, or read `settings.MICBOARD_*` directly.

## Add a setting

1. Add the definition to `micboard/management/commands/init_settings.py`.
2. Choose the narrowest valid scope and a serialized default that matches the declared type.
3. Read it through `micboard_settings.get(...)` with explicit scope objects.
4. Add tests for resolution, scope isolation, authorization and redaction.
5. Initialize definitions with `uv run --no-sync python manage.py init_settings` (`--reset` replaces existing definitions, so use it only in a controlled environment).

## Test it

Cover the explicit default, the definition and `MICBOARD_CONFIG` fallback, scope precedence and isolation, host precedence for `MICBOARD_*` controls, and persistence authorization:

```bash
uv run --no-sync pytest tests/test_settings.py tests/test_settings_service.py \
  tests/services/settings tests/test_settings_architecture.py
```

## Troubleshoot

- **Unexpected deployment value:** inspect the matching Django `MICBOARD_*` setting.
- **Unexpected configurable value:** verify the scope objects passed and the stored row at the definition's scope.
- **Stale value after a supported write:** supported writes invalidate caches, so treat this as a persistence-service defect.
- **Value hidden in the UI:** review the presentation allowlist and the definition's sensitivity.
