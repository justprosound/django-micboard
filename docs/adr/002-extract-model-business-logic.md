# ADR-002: Extract Business Logic from Models to Services

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-05-21
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

1. **Models become pure data holders.** Make `WirelessChassis`, `WirelessUnit`, `RFChannel`, `DiscoveredDevice`, and `ManufacturerConfiguration` side-effect-free. Remove all orchestration logic (sync triggers, status transitions, queue management) from `save()` overrides.
2. **Define a service seam per model.** For each affected model, introduce (or extend) a domain service method that encapsulates the orchestration currently hidden in `save()`. The canonical pattern:

   ```python
   # Callers who want to persist only: use Model.objects.create() / .save()
   # Callers who want to persist AND orchestrate:
   HardwareLifecycleService.save_chassis(chassis_data, context) -> WirelessChassis
   ```

   The `context` parameter carries metadata the caller knows (who triggered the save, what operation scope applies) that the model currently infers through imports.

3. **Model `clean()` / `validate()` methods may keep structural validation** (field formats, required fields, uniqueness) but must not invoke services or write to DB.

4. **Existing post-save signal handlers** must be audited per model. If the logic duplicates a service method, remove the signal and call the service explicitly from the view/task layer instead.

5. **The service layer already has candidates for hosting extracted logic:**
   - `services/core/hardware_lifecycle.py` (381L) — extend for WirelessChassis lifecycle
   - `services/core/hardware.py` (534L) — extend for WirelessChassis CRUD orchestration
   - `services/sync/discovery_candidates_service.py` (321L) — extend for DiscoveredDevice logic

## Consequences

- **Positive:** Models become testable in isolation (no DB side effects). A test of chassis creation no longer implicitly tests discovery orchestration. Business rules are reusable from views, tasks, and management commands alike. Side-effect chains are explicit in the caller — you can see "I'm saving with orchestration" vs "I'm just persisting".
- **Negative:** Existing callers that rely on implicit side-effects from `model.save()` will break. Each caller must be updated to invoke the corresponding service method.

## Migration Summary

All 5 models have been fully extracted. Status per model:

| # | Model | Extraction Scope | Service File | Status |
|---|-------|-----------------|--------------|--------|
| 1 | `ManufacturerConfiguration` | JSON schema validation | `services/discovery/` | ✅ Done |
| 2 | `DiscoveredDevice` | Queue management, duplicate detection | `services/sync/discovered_device_service.py` | ✅ Done |
| 3 | `WirelessUnit` | Status transitions, timestamp updates | `services/hardware/wireless_unit_service.py` | ✅ Done |
| 4 | `RFChannel` | Frequency coordination, regulatory domain resolution | `services/hardware/rf_channel_service.py` | ✅ Done |
| 5 | `WirelessChassis` | `save()` orchestration → 3-5 service methods; band_plan regulatory methods extracted to `chassis_regulatory_service.py` with deprecation shims | `services/hardware/chassis_regulatory_service.py` | ✅ Done |

Note on WirelessChassis: The band_plan regulatory methods (`get_regulatory_domain`, `has_band_plan_regulatory_coverage`, `needs_band_plan_regulatory_update`, `get_band_plan_regulatory_status`) were extracted to a dedicated regulatory service (`chassis_regulatory_service.py`) per **Option B**: all 4 methods in one pass. They share a single-source-of-truth `get_regulatory_domain_for_location(location)` in `rf_channel_service.py`. Model methods remain as deprecation shims delegating to the service.

## Compliance

- CI linting will flag any `save()` method overrides that contain DB writes, external calls, or signal emission.
- New model `save()` overrides require architecture review approval.
