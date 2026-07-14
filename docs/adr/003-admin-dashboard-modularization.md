# ADR-003: Admin Dashboard Modularization

**Status:** Completed
**Date:** 2026-05-20
**Deciders:** Project team

## Context

`micboard/admin/dashboard.py` was 2,431 lines — the single largest file in the project. It contained approximately 50+ HTMX-powered views, inline formsets, JSON endpoints, tabular displays, and chart rendering for the custom Django admin dashboard. The file handled chassis management, wireless unit CRUD, charger display, manufacturer configuration, discovery queue approval, settings diff, monitoring, and gap analysis — all mixed together.

## Decision

Extract each major functional area into its own admin module under `micboard/admin/`. The extraction used the existing domain-based module pattern rather than creating a separate `views/` subdirectory.

## Result

The original dashboard.py views were distributed to per-domain modules:

| Concern | Destination | Notes |
|---|---|---|
| Dashboard overview | Removed | Retained views were never registered and exposed global data |
| Chassis management | `receivers.py` | WirelessChassisAdmin |
| Wireless unit CRUD | `channels.py` | RFChannelAdmin, WirelessUnitAdmin |
| Discovery queue | `discovery_admin.py` | DiscoveryQueueAdmin |
| Charger display | `chargers.py` | ChargerAdmin |
| Manufacturer config | `configuration.py` | ManufacturerConfigurationAdmin |
| Monitoring/alerts | `monitoring.py` | DiscoveredDeviceAdmin, etc. |
| Settings | `settings.py` | SettingDefinitionAdmin |
| Gap analysis | Removed | The admin class and standalone view were never registered |

No backward-compat shims were introduced (per AGENTS.md policy).

## Consequences

- **Positive:** Each module independently navigable and testable. Merge conflicts reduced.
- **Positive:** The reachable admin surface is entirely domain-owned.
- **Known:** `configuration.py` (~240 lines), `receivers.py` (~432 lines) remain slightly over or near the 400-line target.
- **Cleanup (2026-07-14):** Removed the unreachable dashboard and gap-analysis modules, their
  template, DTOs, and tests. Neither module was imported, registered, or routed; retaining them
  would have preserved global unscoped data views as latent security hazards.
