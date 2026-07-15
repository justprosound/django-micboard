# ADR-001: Service Layer Decomposition

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14
**Deciders:** (to be assigned)

## Historical Context

The services layer (`micboard/services/`) contains ~53 files across 10 domain subpackages, totaling ~10,800 lines. Two files are outsized:

- `services/sync/discovery_service.py` — 898 lines, mixing discovery orchestration, dedup logic, device queue management, and network probing.
- `services/core/hardware_lifecycle.py` — 640 lines, mixing CRUD, state transitions, and event emission.

Several other service files (e.g., `hardware.py` at 534 lines, `hardware_deduplication_service.py` at 568 lines) also exceed a healthy module size.

A separate `shared/utils.py` exists but is empty. `shared/base_crud.py` (211 lines) defines a `BaseCRUDService` mixin that is imported but never used. Dead code and oversized modules increase cognitive load and mask responsibility boundaries.

## Decision and Result

We will decompose the services layer following these rules:

1. **Every service file ≤400 lines.** Files exceeding this threshold must be split by operational concern, not by arbitrary chunking.
2. **Discovery orchestration** is split across the canonical modules in `services/sync/`:
   `discovery_service.py`, execution, trigger, queue, claim, approval, configuration, source-cursor,
   and device-promotion services. Each call site imports its owning module directly.
3. **Hardware behavior** is split across `services/core/hardware_lifecycle.py`,
   `hardware_post_save_hooks.py`, and the focused services under `services/hardware/`.
4. **Remove `BaseCRUDService`** — unused abstract class. Do not retain dead code.
5. **Remove empty `utils.py`** — unused placeholder files invite dumping.
6. **All services must have a single, documented responsibility** reflected in their module name.

## Consequences

- **Positive:** Each module becomes navigable in ≤400 lines; responsibility boundaries are explicit; onboarding friction decreases; test surface can target single concerns.
- **Negative:** Import paths change; existing `from discovery_service import X` references must be updated across tasks, admin, and management commands.
- **Migration:** Update all call sites in the same change. No compatibility modules, aliases, or
  package re-exports are retained.

## Compliance

- Run `uv run ruff check . --select=PYL` to flag modules above threshold.
- CI will enforce: no service file >400 lines.
