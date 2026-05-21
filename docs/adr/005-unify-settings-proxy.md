# ADR-005: Unify Settings Proxy

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-05-21
**Deciders:** (to be assigned)

## Context

django-micboard has two parallel settings resolution mechanisms with overlapping concerns:

1. **`micboard/conf.py`** (149 lines) — `MicboardSettingsProxy` reads from `django.conf.settings.MICBOARD_CONFIG` dict, merged with defaults from `AppConfig`. Provides attribute-style access (`config.msp_enabled`). Contains 18 hardcoded property getters for feature flags (msp_enabled, multi_site_mode), limits (global_device_limit), and retention (activity_log_retention_days).
2. **`micboard/services/shared/settings_registry.py`** (292 lines) — `SettingsRegistryService` resolves DB-backed `Setting` values through a scope hierarchy (global → site → organization → manufacturer), with Django cache (TTL: 300s).

Additionally, **~20 files** access `settings.MICBOARD_CONFIG` directly rather than through either proxy, scattering the reading surface across management commands, `apps.py`, `base_http_client.py`, and `services/maintenance/audit.py`.

The dual proxy causes:
- Inconsistent access patterns across the codebase — `conf.py` uses attribute-style, `settings_registry.py` uses `.get(key)`.
- Confusion about which proxy to use for a given setting (a feature flag vs a per-org setting).
- Difficulty auditing where a setting is consumed — direct `settings.MICBOARD_CONFIG` accesses are invisible to both proxies.
- Deletion test: deleting either `conf.py` or `settings_registry.py` doesn't eliminate the problem — the confusion just moves to the surviving module.

## Decision

1. **Consolidate into a single `SettingsService`** under `micboard/services/settings/settings_service.py` with a single public seam:

   ```python
   SettingsService.get(key, scope_hints=None, default=None) -> Any
   ```

   Where `scope_hints` is an optional dict with keys `organization`, `site`, `manufacturer`. Resolution order: `scope_hints` → cache → DB Setting → `settings.MICBOARD_CONFIG` → `AppConfig` default.

2. **`micboard/conf.py` feature flags become registered keys** in the unified service. Each existing property (e.g., `config.msp_enabled`) becomes a `SettingsService.get("msp_enabled")` call.

3. **All direct `settings.MICBOARD_CONFIG` accesses** must be replaced with `SettingsService.get()`. The 18 `conf.py` properties serve as the migration checklist: each maps to a canonical key name.

4. **`micboard/conf.py`** becomes a thin compatibility layer delegating to `SettingsService`, then is deprecated and removed after one release cycle.

5. **Deprecation path:** Add a lint rule forbidding `from django.conf import settings` combined with `settings.MICBOARD_CONFIG` — force migration to the single proxy.

## Consequences

- **Positive:** Single entry point for all configuration reads — one interface to test, one file to audit. Scope semantics centralized. A caller never needs to know whether a setting comes from Django config or the database.
- **Negative:** ~20 files need import and call-site changes. The `conf.py` → `SettingsService.get()` migration requires mapping each of the 18 properties to a canonical key.
- **Migration:** (a) Implement the unified `SettingsService` with both backends, (b) update `micboard/conf.py` to delegate, (c) migrate all direct `settings.MICBOARD_CONFIG` readers file-by-file (track against the 18-property checklist), (d) remove `micboard/conf.py`.

## Compliance

- CI will enforce: no imports of `django.conf.settings` combined with `settings.MICBOARD_CONFIG` in any file outside the settings service.
