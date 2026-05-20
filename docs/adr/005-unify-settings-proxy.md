# ADR-005: Unify Settings Proxy

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

django-micboard has two parallel settings resolution mechanisms with overlapping concerns:

1. **`micboard/conf.py`** (149 lines) — `MicboardSettingsProxy` reads from `django.conf.settings.MICBOARD_CONFIG` dict, merged with defaults from `AppConfig`. Provides attribute-style access (`config.msp_enabled`).
2. **`micboard/services/shared/settings_registry.py`** (292 lines) — `SettingsRegistryService` resolves DB-backed `Setting` values through a scope hierarchy (global → site → organization → manufacturer).

Additionally, many files access `settings.MICBOARD_CONFIG` directly rather than through either proxy, scattering the reading surface across ~20+ files.

The dual proxy causes:
- Inconsistent access patterns across the codebase.
- Confusion about which proxy to use for a given setting.
- Difficulty auditing where a setting is consumed.

## Decision

1. **Consolidate into a single `SettingsService`** under `micboard/services/settings/settings_service.py` that:
   - Reads from `django.conf.settings.MICBOARD_CONFIG` for static Django settings.
   - Reads from `Setting` model for DB-backed dynamic settings.
   - Applies scope hierarchy resolution internally.
   - Provides a unified `.get(key, scope=None, default=None)` API.
2. **`micboard/conf.py`** becomes a thin re-export of the public API from the new `SettingsService`, then is deprecated and removed after one release cycle.
3. **All direct `settings.MICBOARD_CONFIG` accesses** must be replaced with `SettingsService.get()`.
4. **The deprecation path:** Add a lint rule forbidding `from django.conf import settings` + `settings.MICBOARD_CONFIG` — force migration to the single proxy.

## Consequences

- **Positive:** Single entry point for all configuration reads. Scope semantics are centralized. Direct Django settings access is eliminated, making the consumption surface auditable.
- **Negative:** ~20+ files need import and call-site changes.
- **Migration:** (a) Implement the unified `SettingsService`, (b) update `micboard/conf.py` to delegate, (c) migrate all direct `settings.MICBOARD_CONFIG` readers file-by-file, (d) remove `micboard/conf.py`.

## Compliance

- CI will enforce: no imports of `django.conf.settings` + `MICBOARD_CONFIG` in any file outside the settings service.
