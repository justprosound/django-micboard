# ADR-001: Service Layer Decomposition

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

The services layer (`micboard/services/`) contains ~53 files across 10 domain subpackages, totaling ~10,800 lines. Two files are outsized:

- `services/sync/discovery_service.py` — 898 lines, mixing discovery orchestration, dedup logic, device queue management, and network probing.
- `services/core/hardware_lifecycle.py` — 640 lines, mixing CRUD, state transitions, and event emission.

Several other service files (e.g., `hardware.py` at 534 lines, `hardware_deduplication_service.py` at 568 lines) also exceed a healthy module size.

A separate `shared/utils.py` exists but is empty. `shared/base_crud.py` (211 lines) defines a `BaseCRUDService` mixin that is imported but never used. Dead code and oversized modules increase cognitive load and mask responsibility boundaries.

## Decision

We will decompose the services layer following these rules:

1. **Every service file ≤400 lines.** Files exceeding this threshold must be split by operational concern, not by arbitrary chunking.
2. **`discovery_service.py` (898 lines)** splits into:
   - `discovery_service.py` — core scan orchestration and lifecycle
   - `discovery_scanner.py` — network probe and device enumeration
   - `discovery_queue_manager.py` — queue submission, review, and adoption
   - `discovery_mapper.py` — device-to-chassis mapping and dedup
3. **`hardware_lifecycle.py` (640 lines)** splits into:
   - `hardware_lifecycle.py` — state machine and transition orchestration
   - `hardware_events.py` — event emission and signal handling
   - `hardware_validation.py` — pre-transition validation rules
4. **Remove `BaseCRUDService`** — unused abstract class. Do not retain dead code.
5. **Remove empty `utils.py`** — unused placeholder files invite dumping.
6. **All services must have a single, documented responsibility** reflected in their module name.

## Consequences

- **Positive:** Each module becomes navigable in ≤400 lines; responsibility boundaries are explicit; onboarding friction decreases; test surface can target single concerns.
- **Negative:** Import paths change; existing `from discovery_service import X` references must be updated across tasks, admin, and management commands.
- **Migration:** Execute in a single commit with no behavioral change. Each split preserves the public API of the original module by re-exporting from `__init__.py` during a deprecation window, then remove re-exports in a follow-up.

## Compliance

- Run `ruff check . --select=PYL` to flag modules above threshold.
- CI will enforce: no service file >400 lines.
