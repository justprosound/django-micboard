# Settings System Summary

Micboard settings are split by responsibility without exposing parallel public APIs.

## Modules

| Responsibility | Owning module |
|---|---|
| Runtime resolution and public cache controls | `micboard/services/settings/settings_service.py` |
| Internal scoped lookup and cache mechanics | `micboard/services/settings/registry.py` |
| Authorized typed writes | `micboard/services/settings/persistence_service.py` |
| Tenant-visible projections and redaction | `micboard/services/settings/presentation_service.py` |
| Role and scope visibility | `micboard/services/settings/visibility_service.py` |
| Definitions and stored values | `micboard/models/settings/registry.py` |

Runtime callers import the `settings` singleton from `settings_service.py`. The internal registry is an implementation detail and provides no public write or bulk-read facade.

## Resolution contract

- `MICBOARD_*` deployment controls and named feature properties are host-owned.
- Other keys consult only the database scope declared by their active definition.
- Missing database values fall through `MICBOARD_CONFIG`, package defaults, definition defaults, and finally the caller default.
- Supported writes validate the setting definition and tenant scope before upsert.
- Presentation services redact sensitive values and use fixed query budgets.

## Administration

Standard definitions are created with:

```bash
uv run --no-sync python manage.py init_settings
```

Administrators use the Django admin or the bulk/manufacturer settings views. Both paths delegate to the same persistence service and invalidate value and definition caches after successful writes.

## Guardrails

- An AST test rejects direct `MICBOARD_*` reads outside `SettingsService`.
- Tests assert the removed shared-registry path and feature-flag facade cannot be imported.
- Forms, views, and admin code do not write `Setting` rows directly.
- No compatibility modules or re-exports preserve deleted settings APIs.

## Verification

```bash
uv run --no-sync pytest tests/test_settings.py tests/test_settings_service.py \
  tests/services/settings tests/test_settings_architecture.py
uv run --no-sync ruff check micboard/services/settings tests/services/settings
uv run --no-sync python -m mypy micboard/services/settings
```

See [Settings Management](settings-management.md) for usage and [ADR-005](../adr/005-unify-settings-proxy.md) for the decision.
