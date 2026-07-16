<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Service Layer Decomposition

## Project Description

The django-micboard services layer comprised ~53 files across 10 domain subpackages totaling ~10,800 lines. Two files — `discovery_service.py` (898 lines) and `hardware_lifecycle.py` (640 lines) — mixed orchestration, dedup logic, state transitions, and event emission. Several other service files exceeded 400 lines. A separate `shared/utils.py` was empty and `shared/base_crud.py` (211 lines) defined an unused abstract class. The cognitive load of navigating oversized modules with unclear boundaries masked responsibility drift and prevented targeted testing.

## Project Goals

Decompose the services layer into domain-focused modules each ≤400 lines with single, documented responsibilities. Eliminate dead code (`BaseCRUDService`, empty `utils.py`). Update all call sites in the same change with no compatibility shims. Enforce the 400-line ceiling via CI.

## Technical Uncertainties

### Uncertainty #1: Discovery Orchestration Split Boundaries

**Description:** The 898-line `discovery_service.py` mixed network probing, device queue management, dedup logic, claim/approval workflows, and configuration management. No clear seams existed in the codebase to guide the split.

**Experiments:**
- Spike: extract `discovery_execution_service.py` for pure network probing — reduced cognitive load but left queue/claim coupling
- Spike: extract `discovery_claim_service.py` for approval workflow — revealed hidden dependency on execution service's cursor state
- Adopted: canonical module set in `services/sync/` — execution, trigger, queue, claim, approval, configuration, source-cursor, device-promotion — each importing its owning module directly

**Results / Learnings / Success:**
- 898 lines → 8 modules averaging ~110 lines each
- Call-site update completed in single PR; no compatibility aliases needed
- CI now flags any service file >400 lines (`ruff --select=PYL`)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-001 Service Layer Decomposition](../../adr/001-service-layer-decomposition.md)
- **PRs:** (reference implementation PRs)

### Uncertainty #2: Hardware Lifecycle Split Boundaries

**Description:** The 640-line `hardware_lifecycle.py` mixed CRUD, state transitions, and event emission. Interactions with `hardware.py` (534L) and `hardware_deduplication_service.py` (568L) created a 1,700+ line coupled cluster.

**Experiments:**
- Attempted inheritance-based refactor — created circular dependency between lifecycle and dedup services
- Adopted: split into `chassis_lifecycle_service.py`, `chassis_regulatory_service.py`, `wireless_chassis_persistence_service.py`, `wireless_unit_service.py`, `rf_channel_service.py` under `services/hardware/` — each owning one model's write path

**Results / Learnings / Success:**
- Hardware write paths now single-seam: `WirelessChassisWrite` DTO → `wireless_chassis_persistence_service.py`
- Lifecycle transitions and regulatory coverage isolated in separate modules
- Former `wireless_chassis_service.py` deleted; no compat methods retained

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)
- **PRs:** (reference implementation PRs)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Spike / Implementation | ~40% | Defined split boundaries, wrote ADR-001, executed migration |
| (engineer) | Implementation / Testing | ~30% | Updated call sites, wrote CI enforcement |
| (engineer) | Implementation | ~20% | Hardware service split, DTO design |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-001 Service Layer Decomposition](../../adr/001-service-layer-decomposition.md)
- [ADR-002 Extract Business Logic from Models](../../adr/002-extract-model-business-logic.md)
- [CONTEXT.md](../../development/context.md) (domain architecture reference)

**PRs:**
- (main decomposition PR)
- (hardware service split PR)
- (CI enforcement PR)