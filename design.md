# Design

## Architecture Overview

The app keeps a reusable Django package layout with a configuration registry, manufacturer plugin registry, and optional multitenancy module. Core services resolve settings through a scope-aware registry and use tenant-aware query helpers to keep data isolation consistent.

## Components

- Configuration access: `micboard/conf.py` for feature flags + `micboard/services/settings_registry.py` for scoped settings.
- Manufacturer registry: `micboard/services/plugin_registry.py` and `micboard/services/manufacturer_config_registry.py`.
- Tenant scoping: tenant-aware QuerySet/Manager helpers and middleware that attaches request context.
- Admin overrides view: admin-facing UI showing differences between scoped settings and global defaults.

## Data Flow

1. Request arrives with tenant context resolved via middleware.
2. Services query models using tenant-aware helpers (organization/site/campus).
3. Manufacturer-specific operations resolve plugin + config through registries.
4. Configuration values are resolved using settings registry fallback order.
5. Admin settings diff view computes global value + scoped overrides for display.

## Settings Resolution Order

1. Manufacturer-scoped overrides (if applicable).
2. Site-scoped overrides (if applicable).
3. Organization-scoped overrides (if applicable).
4. Global stored setting value.
5. SettingDefinition default.
6. Caller-provided default.
7. Raise if required.

## Error Handling

- Missing required setting raises a typed error (`SettingNotFoundError`).
- Missing manufacturer plugin logs a warning and returns `None` for plugin lookup.
- Admin settings diff view must handle missing global values safely.

## Security and Multi-tenant Considerations

- Tenant isolation uses middleware + QuerySet helpers.
- Do not expose or log sensitive values in admin diff view.

## Testing Strategy (planned)

- Unit tests for settings resolution order and required behavior.
- Tests for tenant-scoped query helpers used by services.
- Tests for admin settings diff view rendering and access controls.
