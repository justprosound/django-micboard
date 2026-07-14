# PRD-003: Plugin Standardization & Infrastructure Unification

**Status:** In Progress
**Date:** 2026-05-20

## Problem Statement

Manufacturer plugin stacks (Shure: ~1,153 lines, Sennheiser: ~772 lines) are 80-90% structurally identical, with copy-pasted patterns for HTTP clients, rate limiting, retry logic, and data transformation. Two parallel settings resolution mechanisms (`conf.py` and `SettingsRegistryService`) create inconsistent access patterns. A legacy compat shim (`micboard/manufacturers/`) used fragile `sys.modules` patching (removed in ADR-008).

## Goals

1. Extract shared plugin framework reducing per-manufacturer code by 40-60%.
2. Unify all settings access through a single `SettingsService`.
3. Remove the `micboard/manufacturers/` compat shim entirely.
4. Eliminate all direct `settings.MICBOARD_CONFIG` reads (~20+ files).

## Non-Goals

- Adding new manufacturer integrations.
- Changing the plugin registry or discovery mechanism.
- Rewriting database-backed settings model schema.

## Scope

| Area | ADR | Issues |
|------|-----|--------|
| Build shared plugin framework | ADR-004 | #63 |
| Refactor Shure plugin | ADR-004 | #64 |
| Refactor Sennheiser plugin | ADR-004 | #65 |
| Remove compat shim | ADR-008 | #66 |
| Implement unified SettingsService | ADR-005 | #67 |
| Migrate direct settings reads | ADR-005 | #68 |
| Deprecate and remove conf.py | ADR-005 | #76 |

## Design

- **Plugin framework:** Extract `micboard/integrations/common/` with shared HTTP client, base plugin, base discovery client, base transformers, and exception taxonomy. Shure and Sennheiser inherit from these bases, overriding only protocol-specific details.
- **Settings unification:** `SettingsService.get(key, default=None, organization=None, site=None,
  manufacturer=None)` is the single entry point. The former proxy shim is removed, and a lint
  rule forbids direct `settings.MICBOARD_CONFIG` access.
- **Shim removal:** Single PR — delete `micboard/manufacturers/`, update all imports to `micboard.integrations.*`, merge `base.py` into `integrations/common/`.

## Success Metrics

- Shure plugin: ≤500 lines (from ~1,153).
- Sennheiser plugin: ≤400 lines (from ~772).
- No imports from `micboard.manufacturers`.
- No direct `settings.MICBOARD_CONFIG` reads outside `SettingsService`.
- `uv run ruff check .` and `uv run pytest` pass.

## Risks

- **Protocol divergence:** Shure uses WebSocket for streaming; Sennheiser uses SSE. Base classes must be overridable at the method level to accommodate this.
- **Import chain disruption:** Shim removal and settings migration must be coordinated to avoid broken CI mid-migration.
- **Missed settings readers:** May discover additional direct `settings.MICBOARD_CONFIG` reads during migration — plan for iterative cleanup.

## Issues

- #63 — refactor: build shared plugin framework in integrations/common/
- #64 — refactor: refactor Shure plugin to use shared base classes
- #65 — refactor: refactor Sennheiser plugin to use shared base classes
- #66 — chore: remove micboard/manufacturers/ compat shim
- #67 — refactor: implement unified SettingsService
- #68 — refactor: migrate all direct settings.MICBOARD_CONFIG reads
- #76 — chore: remove the obsolete settings proxy

## References

- ADR-004: Standardize Manufacturer Plugin System
- ADR-005: Unify Settings Proxy
- ADR-008: Remove Compat Shim
