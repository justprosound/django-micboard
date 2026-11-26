---
title: "Settings management"
description: "How micboard settings are read, scoped, written and cached."
type: reference
audience: developer
---
Micboard exposes one runtime read interface and one authorized write workflow. Application code must not import the internal registry or read `MICBOARD_*` values directly from Django settings. For the decision behind this, see [ADR-005](../adr/005-unify-settings-proxy.md). For the standard keys, see [Setting definitions reference](settings-quick-reference.md).

## Owning modules

| Responsibility | Module |
| --- | --- |
| Runtime resolution and public cache controls | `micboard/services/settings/settings_service.py` |
| Internal scoped lookup and cache mechanics | `micboard/services/settings/registry.py` |
| Authorized typed writes | `micboard/services/settings/persistence_service.py` |
| Tenant-visible projections and redaction | `micboard/services/settings/presentation_service.py` |
| Role and scope visibility | `micboard/services/settings/visibility_service.py` |
| Definitions and stored values | `micboard/models/settings/registry.py` |

Runtime callers import the `settings` singleton from `settings_service.py`.

## Resolution order

1. The Django host setting, for `MICBOARD_*` deployment controls and the named feature properties such as `msp_enabled`. These are host-owned: a database row cannot override them.
2. The stored value at the one scope the active `SettingDefinition` declares (global, organization, site or manufacturer). A manufacturer definition consults only the manufacturer passed in, and values never fall through between scopes.
3. The host `MICBOARD_CONFIG` value.
4. The package default.
5. The `SettingDefinition` default.
6. The default passed by the caller.

## Definitions and values

`SettingDefinition` declares a key, value type, allowed scope, default and optional choices. `Setting` stores one serialized value for one global, organization, site or manufacturer scope. Database constraints reject duplicate scope rows, and persistence validation rejects incompatible scope combinations.

## Interfaces

- `/admin/micboard/settingdefinition/`: definitions
- `/admin/micboard/setting/`: scoped values
- `/settings/`: redacted overview
- `/settings/bulk/`: authorized bulk changes
- `/settings/manufacturer/`: manufacturer-scoped changes

All writes go through `SettingsPersistenceService`, which checks authorization and scope, serializes the value, and invalidates the value and definition caches. `settings.invalidate_value_cache(key)` and `settings.invalidate_definition_cache(key)` exist for infrastructure code inside the settings domain.

## Guardrails

An AST test (`tests/test_settings_architecture.py`) rejects direct `MICBOARD_*` reads outside `SettingsService`. Forms, views and admin code do not write `Setting` rows directly. Presentation services redact sensitive values.
