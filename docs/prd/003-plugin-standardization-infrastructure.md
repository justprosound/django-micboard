# PRD-003: Plugin Standardization & Infrastructure Unification

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14

## Problem Statement

Manufacturer integrations need common transport, retry, rate-limit, health, plugin-loading, and
exception behavior without hiding protocol differences behind a broad inheritance tree. Shure uses
REST and WebSocket transports; Sennheiser SSCv2 uses REST and SSE, with different discovery and
payload contracts. Two parallel settings mechanisms and the legacy `micboard/manufacturers/` shim
also created ambiguous import and configuration paths.

## Goals

1. Establish one verified transport and plugin-contract seam under `micboard/services/common/base/`.
2. Unify all settings access through a single `SettingsService`.
3. Remove the `micboard/manufacturers/` compat shim entirely.
4. Eliminate all direct `settings.MICBOARD_CONFIG` reads (~20+ files).
5. Keep protocol-specific clients, discovery, transforms, and streaming adapters manufacturer-local.

## Non-Goals

- Adding new manufacturer integrations.
- Changing the plugin registry or discovery mechanism.
- Rewriting database-backed settings model schema.

## Scope

| Area | ADR | Issues |
|------|-----|--------|
| Establish shared transport and plugin contracts | ADR-004 | #63 |
| Keep Shure protocol behavior local | ADR-004 | #64 |
| Keep Sennheiser protocol behavior local | ADR-004 | #65 |
| Remove compat shim | ADR-008 | #66 |
| Implement unified SettingsService | ADR-005 | #67 |
| Migrate direct settings reads | ADR-005 | #68 |
| Deprecate and remove conf.py | ADR-005 | #76 |

## Design

- **Shared contracts:** Keep verified HTTP transport, bounded responses, retries, circuit breaking,
  health behavior, rate limiting, and plugin interfaces in `micboard/services/common/base/`; keep the
  exception hierarchy in `micboard/exceptions.py`.
- **Convention-based loading:** `PluginRegistry` delegates class discovery to
  `get_manufacturer_plugin(code)`, which imports `micboard.integrations.<code>.plugin` and selects the
  conventionally named concrete `ManufacturerPlugin` subclass. There is no central plugin map.
- **Protocol ownership:** Shure and Sennheiser retain manufacturer-local device, discovery,
  transform, and streaming adapters. Only transport-neutral behavior with two verified consumers is
  shared.
- **Settings unification:** `SettingsService.get(key, default=None, organization=None, site=None,
  manufacturer=None)` is the single entry point. The former proxy shim is removed, and a lint
  rule forbids direct `settings.MICBOARD_CONFIG` access.
- **Shim removal:** Delete `micboard/manufacturers/`, update imports to defining modules, and use
  shared contracts directly from `micboard.services.common.base` without compatibility exports.

## Success Metrics

- Shared transport and plugin behavior has one canonical implementation under `services/common/base/`.
- Protocol-specific integrations remain independently testable and locally readable.
- Plugin discovery requires no registry-map edit for a new conventionally named integration.
- No imports from `micboard.manufacturers`.
- No direct `settings.MICBOARD_CONFIG` reads outside `SettingsService`.
- `uv run ruff check .` and `uv run pytest` pass.

## Risks

- **Protocol divergence:** Broad shared discovery or transformer bases would obscure vendor-specific
  semantics. Keep those adapters local and extract only proven common behavior.
- **Import chain disruption:** Shim removal and settings migration must be coordinated to avoid broken CI mid-migration.
- **Missed settings readers:** May discover additional direct `settings.MICBOARD_CONFIG` reads during migration — plan for iterative cleanup.

## Issues

- #63 — refactor: establish shared transport and plugin contracts
- #64 — refactor: align Shure with shared transport contracts
- #65 — refactor: align Sennheiser with shared transport contracts
- #66 — chore: remove micboard/manufacturers/ compat shim
- #67 — refactor: implement unified SettingsService
- #68 — refactor: migrate all direct settings.MICBOARD_CONFIG reads
- #76 — chore: remove the obsolete settings proxy

## References

- ADR-004: Compose Manufacturer Plugins Around Shared Transport
- ADR-005: Unify Settings Proxy
- ADR-008: Remove Compat Shim
