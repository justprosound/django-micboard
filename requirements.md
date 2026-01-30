# Requirements

## Scope

This release prep focuses on refactoring the reusable app for maintainability and safety without modifying database migrations.

## EARS Requirements

- THE SYSTEM SHALL avoid changes to any existing migration files under micboard/migrations/.
- WHEN the app resolves configuration values, THE SYSTEM SHALL use a scope-aware settings registry with inheritance (global → organization → site → manufacturer).
- WHEN a configuration value is missing at all scopes AND is marked required, THE SYSTEM SHALL raise a clear, typed error.
- WHEN the admin user views settings overrides, THE SYSTEM SHALL display where scoped values differ from global defaults.
- WHEN multi-tenant mode is enabled, THE SYSTEM SHALL apply tenant scoping consistently for list and lookup queries that are tenant-bound.
- WHEN multi-site mode is enabled, THE SYSTEM SHALL apply site scoping consistently for tenant-bound queries.
- WHEN manufacturer-specific behavior is needed, THE SYSTEM SHALL use a manufacturer-agnostic registry or plugin lookup rather than hard-coded vendor branches.
- IF a vendor integration is missing, THEN THE SYSTEM SHALL fail gracefully with a clear log message without crashing the request.
- WHEN releasing the reusable app, THE SYSTEM SHALL include templates and static assets in packaging metadata.

## Constraints

- No database schema changes; migrations must remain untouched.
- Maintain backwards compatibility for existing APIs and configuration keys where possible.
