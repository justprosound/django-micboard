# ADR-002: Extract Business Logic from Models to Services

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14
**Deciders:** (to be assigned)

## Context

Several model classes in `micboard/models/` contain business logic embedded in `save()` overrides, `clean()` methods, and property methods. The largest offender is `models/hardware/wireless_chassis.py` at 709 lines — the single largest file in the entire codebase — which mixes data persistence with discovery side-effects, lifecycle transitions, and network state management.

Affected models and their embedded logic:

| Model | File | Lines | Embedded Logic |
|-------|------|-------|----------------|
| `WirelessChassis` | `models/hardware/wireless_chassis.py` | 709 | `save()` (~80L) updates device status, triggers sync, manages network state transitions; django-lifecycle hooks handle state management |
| `WirelessUnit` | `models/hardware/wireless_unit.py` | 449 | `save()` overrides for status transitions, timestamp updates |
| `RFChannel` | `models/rf_coordination/rf_channel.py` | 347 | Lifecycle hooks for frequency coordination side-effects |
| `DiscoveredDevice` | `models/discovery/registry.py` | 353 | `save()` does duplicate detection and queue management |
| `ManufacturerConfiguration` | `models/discovery/configuration.py` | 213 | `validate()` (~60L) does JSON schema validation and error collection |

Additionally, several models use `post_save` signals that duplicate logic already present in service-layer methods in `services/core/hardware_lifecycle.py` (381L) and `services/core/hardware.py` (534L). A developer modifying `WirelessChassis.save()` must understand the full chain: model → django-lifecycle hook → signal → service, which is implicit and untestable in isolation.

This violates the single-responsibility principle. Models should define data structure, constraints, and query scope — not orchestrate side effects. Embedding business logic in models makes it:
- Impossible to test business rules without DB setup.
- Difficult to reuse logic outside model lifecycle (e.g., in bulk operations).
- Hard to reason about side-effect chains (save triggers signal triggers service).

## Decision

1. **Models do not override persistence with orchestration.** `WirelessChassis`, `WirelessUnit`,
   `RFChannel`, `DiscoveredDevice`, and `ManufacturerConfiguration` keep persistence methods free
   of service imports and external calls.
2. **Define a service seam per model.** For each affected model, introduce (or extend) a domain service method that encapsulates the orchestration currently hidden in `save()`. The canonical pattern:

   ```python
   # Explicit workflows call their domain service:
   HardwareLifecycleService.save_chassis(chassis_data, context) -> WirelessChassis
   ```

   The `context` parameter carries metadata the caller knows (who triggered the save, what operation scope applies) that the model currently infers through imports.

3. **Model `clean()` / `validate()` methods may keep structural validation** (field formats, required fields, uniqueness) but must not invoke services or write to DB.

4. **Django lifecycle adapters preserve repository-wide invariants.** `model_lifecycle.py` owns the
   registered pre/post-save and delete adapters. They delegate validation, derived-field updates,
   audit, broadcast, and discovery scheduling to domain services. Consequently, ordinary
   `.save()` is not a persistence-only escape hatch; callers needing bulk persistence without
   lifecycle behavior must use an explicit reviewed service path.

5. **The service layer already has candidates for hosting extracted logic:**
   - `services/core/hardware_lifecycle.py` (381L) — extend for WirelessChassis lifecycle
   - `services/core/hardware.py` (534L) — extend for WirelessChassis CRUD orchestration
   - `services/sync/discovery_sync_service.py` — orchestrates claimed discovery synchronization

6. **Route chassis field persistence through one seam.** Manufacturer sync, discovery approval,
   promotion, imports, refresh, realtime updates, lifecycle creation, and regulatory repair pass a
   `WirelessChassisWrite` DTO to
   `services/hardware/wireless_chassis_persistence_service.py`. Lifecycle transition methods remain
   responsible for status policy, but callers no longer create or upsert chassis rows themselves.

## Consequences

- **Positive:** Models remain declarative while lifecycle behavior has one registered adapter and
  domain-service implementation. Direct and service-driven writes obey the same invariants.
- **Positive:** Chassis identity validation, database alias selection, explicit-field updates, and
  normalized manufacturer persistence have one implementation.
- **Negative:** Save behavior still includes delegated lifecycle effects. Developers must inspect
  `model_lifecycle.py` when changing write semantics and must use the documented suppression
  context only in reviewed bulk workflows.

## Migration Summary

All 5 models have been fully extracted. Status per model:

| # | Model | Extraction Scope | Service File | Status |
|---|-------|-----------------|--------------|--------|
| 1 | `ManufacturerConfiguration` | JSON schema validation | `services/discovery/` | ✅ Done |
| 2 | `DiscoveredDevice` | Queue management, duplicate detection | `services/sync/discovered_device_service.py` | ✅ Done |
| 3 | `WirelessUnit` | Status transitions, timestamp updates | `services/hardware/wireless_unit_service.py` | ✅ Done |
| 4 | `RFChannel` | Frequency coordination, regulatory domain resolution | `services/hardware/rf_channel_service.py` | ✅ Done |
| 5 | `WirelessChassis` | Save transitions and side effects; band-plan detection and coverage | `services/hardware/chassis_lifecycle_service.py`, `services/hardware/chassis_regulatory_service.py` | ✅ Done |

Note on WirelessChassis: save transition validation, uptime derivation, audit, and committed
broadcasts live in `chassis_lifecycle_service.py`. Device specification and band-plan enrichment,
detection, and regulatory coverage live in `chassis_regulatory_service.py`. Regulatory-domain
lookup uses the defining `rf_channel_service.get_regulatory_domain_for_location()` implementation.
The former mixed `wireless_chassis_service.py` module was deleted; callers import each owning
module directly and no compatibility methods remain.

## Compliance

- CI linting will flag any `save()` method overrides that contain DB writes, external calls, or signal emission.
- New model `save()` overrides require architecture review approval.
