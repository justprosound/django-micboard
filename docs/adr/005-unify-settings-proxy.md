# ADR-005: Unify Settings Proxy

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-13
**Deciders:** (to be assigned)

## Context

django-micboard previously had two parallel settings resolution mechanisms with overlapping
concerns:

1. **The removed runtime settings proxy** read from the host `MICBOARD_CONFIG` dictionary and
   exposed overlapping convenience properties.
2. **`micboard/services/shared/settings_registry.py`** (292 lines) — `SettingsRegistryService` resolves DB-backed `Setting` values through a scope hierarchy (global → site → organization → manufacturer), with Django cache (TTL: 300s).

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
   values. Resolution then falls back through the host configuration dictionary, feature flags,
   app defaults, and the caller's explicit default.

2. **Former proxy feature flags become registered keys** in the unified service. Callers use
   `settings.get("msp_enabled")` or the corresponding convenience property.

3. **All direct host configuration reads** outside `SettingsService` are replaced with
   `SettingsService.get()` or `SettingsService.get_config_dict()`.

4. **Remove the obsolete settings proxy without a compatibility layer.** All callers import the
   public singleton or service class from `micboard.services.settings`.

5. **Enforcement:** Add a lint rule forbidding raw host configuration reads outside the unified
   service.

## Consequences

- **Positive:** Single entry point for all configuration reads — one interface to test, one file to audit. Scope semantics centralized. A caller never needs to know whether a setting comes from Django config or the database.
- **Negative:** Existing callers must move directly to the canonical service API.
- **Migration:** Implement the unified service, migrate every caller, and delete the obsolete
  proxy rather than retaining a compatibility shim.

## Compliance

- CI will enforce: no imports of `django.conf.settings` combined with `settings.MICBOARD_CONFIG` in any file outside the settings service.
