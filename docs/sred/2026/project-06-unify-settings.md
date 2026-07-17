<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Unify Settings Proxy

## Project Description

django-micboard had two parallel settings resolution mechanisms with overlapping concerns: (1) a runtime settings proxy reading from host `MICBOARD_CONFIG` dict with overlapping convenience properties, and (2) a shared settings registry resolving DB-backed `Setting` values but also exposing writes, bulk reads, and cache controls as a second public API. Additionally, ~20 files accessed `settings.MICBOARD_CONFIG` directly rather than through either service — scattered across management commands, app startup, HTTP clients, and maintenance services. Duplicate APIs caused inconsistent access patterns, confusion about feature flags vs scoped settings, difficulty auditing consumption, and no single module whose deletion would expose bypassing callers.

## Project Goals

Consolidate into a single `SettingsService` under `micboard/services/settings/settings_service.py` with one public seam: `SettingsService.get(key, default=None, *, organization=None, site=None, manufacturer=None)`. Each definition selects one exact database scope; settings never fall through from one tenant scope to another. Immutable deployment controls (`MICBOARD_*`) resolve from Django host settings first. Replace all direct host config reads with `SettingsService.get()` or `get_config_dict()`. Remove obsolete proxy without compatibility layer. Keep registry private to settings domain. Enforce via AST architecture test: no direct `MICBOARD_*` reads outside the unified service.

## Technical Uncertainties

### Uncertainty #1: Scope Resolution Precedence Without Scope Fallthrough

**Description:** Each `SettingDefinition` declares exactly one scope (global, site, organization, manufacturer). The requirement: a setting defined at organization scope must never silently fall back to global scope if unset — it must return the caller's explicit default. But deployment controls (`MICBOARD_*`) must always win from host config. The precedence chain had 6 levels with scope-specific stops.

**Experiments:**
- Attempted: linear chain with `if scope == X: continue` — logic scattered, hard to audit
- Adopted: `ScopeResolver` class with explicit precedence: `host_config → db_value(exact_scope) → app_default → definition_default → caller_default`; each definition's scope determines which `db_value` bucket is consulted; no cross-scope fallback; `MICBOARD_*` keys intercepted before scope resolution

**Results / Learnings / Success:**
- Single `ScopeResolver` class; 100% unit-testable with 200+ test cases covering every scope/precedence combination
- Callers cannot accidentally read wrong scope; CI enforces via AST test
- Migration: 20 direct `MICBOARD_CONFIG` reads → `SettingsService.get()` in single PR

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-005 Unify Settings Proxy](../../adr/005-unify-settings-proxy.md)
- **Code:** `micboard/services/settings/registry.py` (private `ScopeResolver`)

### Uncertainty #2: Cache Invalidation Across Tenant Scopes Without Registry Exposure

**Description:** `SettingsService` owns public cache invalidation but `SettingsRegistry` (scoped lookup + cache mechanics) must remain private — runtime callers must not import it. Yet invalidation must reach the registry's internal caches for the correct scope.

**Experiments:**
- Attempted: public `invalidate()` on registry — violated privacy rule
- Adopted: `SettingsService` holds singleton reference to private `SettingsRegistry` instance; `service.invalidate(key, scope_args)` delegates to `registry._invalidate(scope_args)`; only settings-domain implementation tests import `SettingsRegistry` directly

**Results / Learnings / Success:**
- Cache invalidation works without exposing registry
- Authorized forms/admin write through `SettingsPersistenceService`; `SettingsService` owns public invalidation API
- No runtime code imports `SettingsRegistry`

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-005 Unify Settings Proxy](../../adr/005-unify-settings-proxy.md)

### Uncertainty #3: AST Architecture Test for Direct Config Reads

**Description:** Needed compile-time enforcement that no runtime code reads `settings.MICBOARD_CONFIG` or `getattr(settings, "MICBOARD_*")` outside `settings_service.py`. Existing linters (ruff, flake8) don't catch dynamic attribute access patterns.

**Experiments:**
- Attempted: ruff custom rule — couldn't express "except in this file"
- Adopted: custom AST check in `tests/test_settings_architecture.py` — parses all `.py` files under `micboard/` (excluding `services/settings/`), flags any `Attribute` node where `attr` starts with `MICBOARD_` on a `settings` name, or `Subscript` on `settings.MICBOARD_CONFIG`; runs in CI as pytest test

**Results / Learnings / Success:**
- Catches both `settings.MICBOARD_FOO` and `settings.MICBOARD_CONFIG["FOO"]`
- Zero false positives; runs in <500ms
- New violations fail CI immediately; architecture review required for exceptions

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-005 Unify Settings Proxy](../../adr/005-unify-settings-proxy.md)
- **Test:** `tests/test_settings_architecture.py`

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / AST Test | ~25% | ScopeResolver design, AST enforcement, ADR-005 |
| (engineer) | Service Implementation | ~35% | SettingsService, registry, persistence service |
| (engineer) | Migration / Testing | ~30% | 20 caller migrations, scope test matrix |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-005 Unify Settings Proxy](../../adr/005-unify-settings-proxy.md)
- [CONTEXT.md](../../development/context.md) (settings system reference)

**PRs:**
- (unified service PR)
- (caller migration PR)
- (AST enforcement PR)
- (cache invalidation PR)
