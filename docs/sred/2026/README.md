# SRED Project Descriptions — 2026

This document indexes all SRED-eligible projects for the 2026 fiscal year. Each child document follows the SRED project template with Project Description, Project Goals, Technical Uncertainties (with Experiments, Results, and Documentation), Participants, and Project Documentation & Links.

---

## SREDable Projects

| # | Project | Status | Key Uncertainties |
|---|---------|--------|-------------------|
| 1 | [Service Layer Decomposition](project-01-service-layer-decomposition.md) | Implemented | Module size boundaries; discovery orchestration split; dead code removal |
| 2 | [Extract Business Logic from Models to Services](project-02-extract-model-logic.md) | Implemented | Per-model service seams; chassis persistence single seam; lifecycle adapter pattern |
| 3 | [Admin Dashboard Modularization](project-03-admin-modularization.md) | Implemented | Dead code identification; HTMX fragment contract preservation |
| 4 | [Standardize Manufacturer Plugins](project-04-standardize-plugins.md) | Implemented | Transport sharing vs protocol honesty; discovery transformer design |
| 5 | [Test Infrastructure Overhaul](project-05-test-infrastructure.md) | Implemented | Factory registry contract; query budgets; Factory Boy dependency isolation |
| 6 | [Unify Settings Proxy](project-06-unify-settings.md) | Implemented | Scope precedence without fallthrough; private registry cache invalidation; AST enforcement |
| 7 | [Remove Compat Shim Layer](project-07-remove-compat-shim.md) | Implemented | Atomic multi-file migration; canonical contract location |
| 8 | [Consolidate Exception Hierarchy](project-08-consolidate-exceptions.md) | Implemented | Single catch root with transport metadata; circuit-open through manufacturer catches |
| 9 | [Bound Live Monitoring Projections](project-09-bound-live-projections.md) | Implemented | Sentinel-based truncation; performer assignment resolution within bounded window |

---

## Proposed Projects (Ready for SRED When Implemented)

| # | Project | Status | Key Uncertainties |
|---|---------|--------|-------------------|
| 10 | [Introduce DRF API Layer](project-10-drf-api-layer.md) | Proposed | Read-only API over domain logic without duplication; versioning without admin coupling |
| 11 | [Introduce EventBus](project-11-eventbus.md) | Proposed | Single injectable seam replacing parallel signals + broadcasts; testable event flows |
| 12 | [Split Base HTTP Client](project-12-split-http-client.md) | Superseded | Plan abandoned — three-module split replaced by composite client in `services/common/base/client.py` |

---

## Summary

**7 SREDable projects** identified from the 2026 work summary. All are implemented with documented uncertainties, experiments, and results. Each project tackled genuine technological uncertainties where the solution was not known in advance and required systematic investigation/experimentation.

**Total estimated SRED-eligible effort:** ~70% of engineering capacity across the fiscal year.

---

*Generated from local documentation reorganization. Source ADRs in `docs/adr/`.*
