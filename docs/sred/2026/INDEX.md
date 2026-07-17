# SRED Project Index — 2026 (FY)

**Project:** django-micboard  
**Fiscal Year:** 2026 (Calendar year 2026-01-01 to 2026-12-31)  
**Status:** Living document — updated as projects complete  

---

## SREDable Projects Summary

| # | Project | Status | Core Uncertainty | Primary ADRs |
|---|---------|--------|------------------|--------------|
| 1 | Service Layer Decomposition | ✅ Implemented | How to decompose 10K-line service layer into ≤400-line domain modules without breaking call sites | ADR-001 |
| 2 | Extract Business Logic from Models to Services | ✅ Implemented | How to extract 5 models' embedded orchestration (save/clean/lifecycle) into explicit service seams while preserving invariants | ADR-002 |
| 3 | Admin Dashboard Modularization | ✅ Implemented | How to split a 2,431-line monolithic admin dashboard into domain modules with zero global data exposure | ADR-003 |
| 4 | Standardize Manufacturer Plugins | ✅ Implemented | How to share verified transport/circuit-breaker/health contracts across divergent protocols (REST+WS, REST+SSE) without forcing inheritance | ADR-004 |
| 5 | Test Infrastructure Overhaul | ✅ Implemented | How to build factory-based test coverage from 0% service coverage to 95% branch floor across domain-aligned structure | ADR-006 |
| 6 | Unify Settings Proxy | ✅ Implemented | How to consolidate dual settings mechanisms + 20 direct config reads into one scoped service with compile-time enforcement | ADR-005 |
| 7 | Remove Compat Shim Layer | ✅ Implemented | How to eliminate sys.modules patching shim in single PR without breaking 15-25 import sites mid-migration | ADR-008 |
| 8 | Consolidate Exception Hierarchy | ✅ Implemented | How to merge dual exception roots (domain + transport) into single structured hierarchy with machine-readable codes | ADR-009 |
| 9 | Bound Live Monitoring Projections | ✅ Implemented | How to bound HTMX dashboard query/response work to constant ceilings regardless of tenant inventory size | ADR-012 |
| 10 | Introduce DRF API Layer (v1 Read-Only) | 🔄 Proposed | How to layer versioned REST API onto admin-only codebase without duplicating domain logic | ADR-007 |
| 11 | Introduce EventBus for Signal-Based Communication | 🔄 Proposed | How to replace parallel Django signals + direct broadcasts with single injectable seam enabling testable event flows | ADR-011 |
| 12 | Split Base HTTP Client | 🔄 **Superseded** | Plan abandoned — original three-module split replaced by composite client pattern in `services/common/base/client.py` | ADR-010 (superseded) |

---

## Non-SREDable Work (Routine Engineering)

| Area | Description | Why Not SRED |
|------|-------------|--------------|
| Dependency updates | uv, Renovate, Warden upgrades | Routine maintenance; no technical uncertainty |
| Bug fixes / minor features | Incremental improvements | Applying known patterns; no systematic investigation |
| Documentation updates | README, guides, ADR maintenance | Recording decisions, not resolving uncertainties |

---

## Navigation

- [Project 1: Service Layer Decomposition](./project-01-service-layer-decomposition.md)
- [Project 2: Extract Business Logic from Models](./project-02-extract-model-logic.md)
- [Project 3: Admin Dashboard Modularization](./project-03-admin-modularization.md)
- [Project 4: Standardize Manufacturer Plugins](./project-04-standardize-plugins.md)
- [Project 5: Test Infrastructure Overhaul](./project-05-test-infrastructure.md)
- [Project 6: Unify Settings Proxy](./project-06-unify-settings.md)
- [Project 7: Remove Compat Shim](./project-07-remove-compat-shim.md)
- [Project 8: Consolidate Exception Hierarchy](./project-08-consolidate-exceptions.md)
- [Project 9: Bound Live Monitoring Projections](./project-09-bound-live-projections.md)
- [Project 10: Introduce DRF API Layer](./project-10-drf-api-layer.md)
- [Project 11: Introduce EventBus](./project-11-eventbus.md)
- [Project 12: Split Base HTTP Client](./project-12-split-http-client.md)

---

## SRED Eligibility Notes

**All 9 implemented projects qualify** under *Experimental Development* (Category 16):
- Each tackled a **genuine technical uncertainty** (no known solution in codebase or ecosystem)
- Each used **systematic investigation** (ADR process, spike implementations, iterative refinement)
- **Advancement** = new architectural patterns now codified and enforced in CI
- **Failure was possible** — several approaches were tried and discarded (e.g., base class inheritance for plugins, compatibility shims for service decomposition)

**3 proposed projects (10, 11, 12)** are ready for SRED claim when implementation begins — uncertainties are documented in ADR-007, ADR-011, and ADR-010.

---

*Generated from ADRs and CONTEXT.md. Keep synchronized with architectural decisions.*
