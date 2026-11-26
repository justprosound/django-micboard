---
title: "ADR-002: Models declare data, services decide behavior"
description: "Why models stay persistence-only and write workflows live in domain services."
type: explanation
audience: developer
---

## Context

Models such as `WirelessChassis`, `WirelessUnit`, `RFChannel`, `DiscoveredDevice` and `ManufacturerConfiguration` used to run discovery, status transitions and network side effects inside `save()`. A change to one write meant tracing model, lifecycle hook, signal and service together, and no rule could be tested without the database.

## Decision

- Models define structure, constraints and structural validation (`clean()`). They do not import services or call out.
- Orchestration lives in domain services: `micboard/services/hardware/chassis_lifecycle_service.py` (transitions, uptime, audit, broadcasts), `chassis_regulatory_service.py` (band-plan and coverage), `rf_channel_service.py`, `wireless_unit_service.py` and `micboard/services/sync/discovered_device_service.py`.
- `micboard/model_lifecycle.py` registers the single set of pre/post-save and delete adapters. They delegate to those services, so an ordinary `.save()` and a service-driven write obey the same rules. Bulk work that must skip the hooks uses the reviewed suppression context (`suppress_chassis_delete_hooks`), as `micboard/services/hardware/chassis_bulk_delete_service.py` does after its authorization check.
- Every path that writes chassis fields passes a `WirelessChassisWrite` DTO to `micboard/services/hardware/wireless_chassis_persistence_service.py`.
- Models declare ownership, not visibility: the ownership lookups in `micboard/models/base_managers.py` and the group-reach table `_REACH` in `micboard/services/shared/visibility.py`. One module decides who may see a row: `visible_to(model, user=...)`, with `restrict_to_tenant_boundary` for the admin.

## Consequences

Models stay declarative and write semantics have one implementation. The cost is that a `save()` still triggers delegated effects, so a developer changing write behavior reads `model_lifecycle.py`. Per-model visibility overrides are not allowed, because they drifted apart and showed different rows on different pages.
