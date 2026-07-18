# SRED Project Summary — 2026 Extract Business Logic from Models to Services

<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

## Project Description

Five Django models embedded orchestration logic in `save()`, `clean()`, and lifecycle hooks: `WirelessChassis` (709 lines — largest model file in the codebase), `WirelessUnit` (449L), `RFChannel` (347L), `DiscoveredDevice` (353L), and `ManufacturerConfiguration` (213L). Business logic included status transitions, sync triggers, duplicate detection, JSON schema validation, and network state management. Additionally, `post_save` signals duplicated logic already present in service-layer methods (`hardware_lifecycle.py` 381L, `hardware.py` 534L). The implicit chain `model.save()` → django-lifecycle hook → signal → service was untestable in isolation and made bulk operations impossible without side effects.

## Project Goals

Extract all orchestration from model persistence methods into explicit domain service seams. Models retain only declarative structure, constraints, and structural validation. Each affected model gets a dedicated service method (e.g., `HardwareLifecycleService.save_chassis()`) with a `context` parameter carrying caller metadata. Route all chassis field persistence through one seam: `WirelessChassisWrite` DTO → `wireless_chassis_persistence_service.py`. Enforce via CI: no `save()` overrides with DB writes, external calls, or signal emission.

## Technical Uncertainties

### Uncertainty #1: WirelessChassis — Disentangling 5 Write Paths into One Seam

**Description:** `WirelessChassis.save()` was invoked by manufacturer sync, discovery approval, promotion, imports, refresh, realtime updates, lifecycle creation, and regulatory repair — each with different context and side-effect requirements. No single service method could express all variants without becoming a god function.

**Experiments:**
- Attempted: single `save_chassis()` with 12 boolean flags — unmaintainable
- Attempted: inheritance hierarchy of save strategies — created circular imports with lifecycle adapters
- Adopted: `WirelessChassisWrite` DTO + `context` dict — callers construct DTO with exact fields + metadata; persistence service applies field updates, lifecycle service handles transitions, regulatory service handles band-plan coverage

**Results / Learnings / Success:**
- 8 write paths → 1 persistence seam + 2 domain services (lifecycle, regulatory)
- `context` carries `triggered_by`, `operation_scope`, `skip_broadcast` — explicit, testable
- Bulk operations use `suppress_lifecycle=True` in context; reviewed and approved

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)
- **PRs:** (implementation PRs per model)

### Uncertainty #2: DiscoveredDevice — Duplicate Detection Without Model Coupling

**Description:** `DiscoveredDevice.save()` performed network-level duplicate detection (MAC/IP matching) and queued items for approval. Moving this to a service required access to the queryset before persistence — but the model's `save()` had already committed the row by the time dedup ran.

**Experiments:**
- Attempted: pre-save signal — still had committed row on race
- Adopted: `DiscoveredDeviceService.claim_or_queue(dto, context)` — creates in transaction with `select_for_update` on candidate set; duplicate → returns existing; unique → creates + queues for approval

**Results / Learnings / Success:**
- Duplicate detection now atomic and testable with fake clock
- Approval workflow decoupled from persistence
- Service unit tests cover race conditions; model `save()` is now 3 lines

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)

### Uncertainty #3: ManufacturerConfiguration — JSON Schema Validation as Pure Function

**Description:** `validate()` (60 lines) embedded `jsonschema` validation with custom error collection. Moving to service required preserving error format for admin forms while making validation a pure, importable function.

**Experiments:**
- Extracted `validate_manufacturer_config(config_dict, schema) -> list[ValidationError]` to `services/discovery/configuration/validation.py`
- Model `clean()` delegates to pure function; service uses same function
- Admin forms catch `ValidationError` and render field-level messages

**Results / Learnings / Success:**
- Validation logic now unit-testable with 200+ schema test cases (no DB)
- Single source of truth for schema validation across admin, API, and sync

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Implementation | ~35% | DTO design, chassis persistence seam, ADR-002 |
| (engineer) | Implementation / Testing | ~30% | DiscoveredDevice service, ManufacturerConfiguration validation |
| (engineer) | Implementation | ~25% | WirelessUnit, RFChannel services, CI rules |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)
- [CONTEXT.md](../../development/context.md) (domain model reference)

**PRs:**
- (per-model extraction PRs: ManufacturerConfiguration, DiscoveredDevice, WirelessUnit, RFChannel, WirelessChassis)
- (CI enforcement PR)
