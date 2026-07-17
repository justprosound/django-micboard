# Design

## Architecture Overview

The app keeps a reusable Django package layout with a configuration registry, manufacturer plugin registry, and optional multitenancy module. Core services resolve settings through a scope-aware registry and use tenant-aware query helpers to keep data isolation consistent.

## Components

- Configuration access: `micboard/services/settings/settings_service.py` for feature flags, host configuration, app defaults, and scoped settings.
- Manufacturer registry: `micboard/services/manufacturer/plugin_registry.py`.
- Tenant scoping: tenant-aware QuerySet/Manager helpers and middleware that attaches request context.
- Admin overrides view: admin-facing UI showing differences between scoped settings and global defaults.

## Data Flow

1. Request arrives with tenant context resolved via middleware.
2. Services query models using tenant-aware helpers (organization/site/campus).
3. Manufacturer-specific operations resolve plugins and scoped settings through their canonical services.
4. Each configuration definition selects one exact scope; missing values use the documented non-database fallback order.
5. Admin settings diff view computes global value + scoped overrides for display.

## Settings Resolution Order

1. Host setting for immutable `MICBOARD_*` deployment controls.
2. Stored value at the definition's exact declared scope.
3. Host `MICBOARD_CONFIG` value.
4. Package default.
5. `SettingDefinition` default.
6. Caller-provided default.

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

## Upcoming Resources

- [Hummingbird Project](https://hummingbird-project.io/) - Core design inspiration for scalable, observable Django applications
