---
title: "ADR-005: One settings service"
description: "Why every runtime configuration read goes through SettingsService."
type: explanation
audience: developer
---

## Context

Configuration used to be read through a runtime settings proxy, a shared registry that also exposed writes, and about twenty direct reads of `settings.MICBOARD_CONFIG`. Callers could not tell which to use, and no single module showed who consumed a setting.

## Decision

- `SettingsService` in `micboard/services/settings/settings_service.py` is the only runtime read seam: `settings.get(key, default, organization=..., site=..., manufacturer=...)`.
- Each setting definition selects one exact database scope, and values never fall through between tenant scopes. `MICBOARD_*` deployment controls and named feature flags resolve only from Django host settings, so a database row cannot weaken a process, transport or security ceiling. Other keys resolve through the stored value, `MICBOARD_CONFIG`, package defaults, the definition default and the caller default.
- `micboard/services/settings/registry.py` is private to the settings domain. Writes go through `SettingsPersistenceService` (`persistence_service.py`), and `SettingsService` owns cache invalidation.
- An architecture test (`tests/test_settings_architecture.py`) rejects direct `MICBOARD_*` reads outside the service.
- No compatibility layer keeps the removed proxy importable.

## Consequences

One interface to test and audit, with scope and precedence rules in one place. Callers must pass explicit scope objects. See [Settings management](../guides/settings-management.md) for the contract.
