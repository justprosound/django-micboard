# Settings Management

Micboard exposes one runtime read interface and one authorized write workflow. Application code
must not import the internal registry or read `MICBOARD_*` values directly from Django settings.

## Runtime reads

```python
from micboard.services.settings.settings_service import settings as micboard_settings

threshold = micboard_settings.get(
    "battery_low_threshold",
    20,
    organization=organization,
    site=site,
    manufacturer=manufacturer,
)
```

For ordinary configurable keys, the definition selects exactly one database scope. A
manufacturer definition consults only the supplied manufacturer, a site definition only the
supplied site, an organization definition only the supplied organization, and a global definition
only the global row. Missing values then fall through `MICBOARD_CONFIG`, package defaults, the
active `SettingDefinition` default, and the supplied default. Values never cascade across scopes.

Keys beginning with `MICBOARD_` are deployment controls. They resolve only from Django host
settings so an administrator cannot weaken a process, transport, or security ceiling with a
database row. Named feature properties such as `msp_enabled` follow the same host-owned rule.

## Runtime writes

Web forms and admin actions submit validated DTOs through
`micboard.services.settings.persistence_service.SettingsPersistenceService`. That service owns
definition lookup, authorization, type serialization, upsert, and cache invalidation. Do not write
`Setting` rows directly from views, forms, commands, or unrelated services.

The supported user interfaces are:

- `/admin/micboard/settingdefinition/` for definitions.
- `/admin/micboard/setting/` for scoped values.
- `/settings/` for the redacted overview.
- `/settings/bulk/` for authorized bulk changes.
- `/settings/manufacturer/` for manufacturer-scoped changes.

## Definitions and scopes

`SettingDefinition` declares a key, value type, allowed scope, default, and optional choices.
`Setting` stores one serialized value for a specific global, organization, site, or manufacturer
scope. Database constraints reject duplicate scope rows; persistence DTO validation rejects
incompatible scope combinations before the write.

Initialize the standard definitions with:

```bash
uv run --no-sync python manage.py init_settings
```

Use `--reset` only when intentionally replacing existing definitions in a controlled environment.

## Caching

`SettingsService` owns cache invalidation. Normal writes invalidate automatically. Infrastructure
code inside the settings domain may call:

```python
micboard_settings.invalidate_value_cache("battery_low_threshold")
micboard_settings.invalidate_definition_cache("battery_low_threshold")
```

Callers outside settings administration should not invalidate caches as part of ordinary reads.

## Adding a setting

1. Add or update the definition in `micboard/management/commands/init_settings.py`.
2. Choose the narrowest valid scope and a serialized default matching the declared type.
3. Read it through `micboard_settings.get(...)` with explicit scope objects.
4. Add resolution, scope-isolation, authorization, and redaction tests.
5. Run the settings architecture test to confirm no alternate read seam was introduced.

## Verification

```bash
uv run --no-sync pytest tests/test_settings.py tests/test_settings_service.py \
  tests/services/settings tests/test_settings_architecture.py
uv run --no-sync ruff check micboard/services/settings tests/services/settings
uv run --no-sync python -m mypy micboard/services/settings
```

## Troubleshooting

- Unexpected deployment value: inspect the matching Django `MICBOARD_*` host setting.
- Unexpected configurable value: verify the requested scope objects and the most-specific active
  database row.
- Stale value after a supported write: treat it as a persistence-service defect; supported writes
  invalidate caches automatically.
- Value hidden in the UI: review the settings presentation allowlist and sensitivity metadata.
