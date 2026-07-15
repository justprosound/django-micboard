# ADR-005: Unify Settings Proxy

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14
**Deciders:** (to be assigned)

## Context

django-micboard previously had two parallel settings resolution mechanisms with overlapping
concerns:

1. **The removed runtime settings proxy** read from the host `MICBOARD_CONFIG` dictionary and
   exposed overlapping convenience properties.
2. **The former shared settings registry** resolved DB-backed `Setting` values but also exposed
   writes, bulk reads, and cache controls as a second public API.

Additionally, **~20 files** accessed `settings.MICBOARD_CONFIG` directly rather than through
either service, scattering the reading surface across management commands, app startup, HTTP
clients, and maintenance services.

The duplicate APIs caused:
- Inconsistent attribute-style and `.get(key)` access patterns.
- Confusion about which API to use for a feature flag versus a scoped setting.
- Difficulty auditing where a setting was consumed.
- No single module whose deletion test exposed bypassing callers.

## Decision

1. **Consolidate into a single `SettingsService`** under `micboard/services/settings/settings_service.py` with a single public seam:

   ```python
   SettingsService.get(
       key,
       default=None,
       *,
       organization=None,
       site=None,
       manufacturer=None,
   ) -> Any
   ```

   The optional scope arguments select organization-, site-, or manufacturer-specific database
   values. Each definition selects one exact database scope; settings never fall through from one
   tenant scope to another. Immutable deployment controls (`MICBOARD_*`) resolve from Django host
   settings first. Other keys resolve through the exact stored value, host configuration
   dictionary, app defaults, definition defaults, and the caller's explicit default.

2. **Former proxy feature flags become registered keys** in the unified service. Callers use
   `settings.get("msp_enabled")` or the corresponding convenience property.

3. **All direct host configuration reads** outside `SettingsService` are replaced with
   `SettingsService.get()` or `SettingsService.get_config_dict()`.

4. **Remove the obsolete settings proxy without a compatibility layer.** All callers import the
   public singleton or service class from its defining module,
   `micboard.services.settings.settings_service`.

5. **Keep the registry private to the settings domain.**
   `micboard/services/settings/registry.py` implements scoped lookup and cache mechanics. Runtime
   callers do not import it. Authorized forms and admin workflows write through
   `SettingsPersistenceService`; `SettingsService` owns public cache invalidation.

6. **Enforcement:** An AST architecture test forbids direct `MICBOARD_*` reads outside the unified
   service.

## Consequences

- **Positive:** Single entry point for all configuration reads — one interface to test, one file
  to audit. Scope semantics and deployment-control precedence are centralized.
- **Negative:** Existing callers must move directly to the canonical service API.
- **Migration:** Implement the unified service, migrate every caller, and delete the obsolete
  proxy rather than retaining a compatibility shim.

## Compliance

- CI enforces no direct `MICBOARD_*` attribute or literal `getattr` reads outside the settings
  service.
- Runtime code does not import `SettingsRegistry`; only settings-domain implementation tests may
  exercise it directly.
