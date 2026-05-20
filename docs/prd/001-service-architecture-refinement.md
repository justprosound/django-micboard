# PRD-001: Service Architecture Refinement

**Status:** Proposed
**Date:** 2026-05-20

## Problem Statement

The services layer (`micboard/services/`) has grown without architectural discipline. Two files exceed healthy module size (discovery_service.py at 898 lines, hardware_lifecycle.py at 640 lines), model `save()` overrides contain orchestration logic that belongs in services, and error handling is inconsistent across domains. Dead code (unused `BaseCRUDService`, empty `utils.py`) adds clutter.

## Goals

1. Every service file ≤400 lines with a single documented responsibility.
2. All model `save()` overrides are idempotent and side-effect-free; business logic lives in services.
3. Consistent exception handling using custom exception classes from `shared/exceptions.py`.

## Non-Goals

- Adding new features.
- Changing public API behavior of existing services.
- Rewriting or deprecating the service layer wholesale.

## Scope

| Area | ADR | Issues |
|------|-----|--------|
| Decompose discovery_service.py and hardware_lifecycle.py | ADR-001 | #51, #53, #54 |
| Extract business logic from model save()/clean() | ADR-002 | #52, #56 |
| Standardize service-layer exception handling | — | #55 |

## Design

- **Split strategy:** Each oversized module splits by operational concern (not arbitrary chunking). Discovery splits into scanner, queue manager, and mapper submodules. Hardware lifecycle splits into events and validation submodules.
- **Extraction strategy:** For each model with embedded logic, (a) introduce a service method, (b) update all call sites, (c) remove the `save()` override.
- **Error strategy:** Audit all service files; replace raw Django/Python exceptions with custom exception classes.
- **Backward compatibility:** Original modules re-export from new submodules via `__init__.py` during a deprecation window, then remove re-exports.

## Success Metrics

- discovery_service.py ≤400 lines
- hardware_lifecycle.py ≤400 lines
- No model `save()` overrides contain DB writes, external calls, or signal emission
- `ruff check .` passes
- All existing tests pass without modification

## Risks

- **Import churn:** ~15-25 call sites across tasks, admin, and management commands need import path updates.
- **Missed callers:** Post-save signal handlers may duplicate service logic — audit required before removal.
- **No test safety net:** 33 of 38 service files have zero tests. PRD-004 addresses this before risky splits.

## Issues

- #51 — chore: remove dead code from services layer
- #52 — refactor: extract business logic from model save()/validate() overrides
- #53 — refactor: decompose discovery_service.py
- #54 — refactor: decompose hardware_lifecycle.py
- #55 — refactor: standardize service-layer error handling
- #56 — refactor: audit and migrate post-save signal handlers

## References

- ADR-001: Service Layer Decomposition
- ADR-002: Extract Business Logic from Models to Services
