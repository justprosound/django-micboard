# ADR-008: Remove Compat Shim Layer

**Status:** Implemented
**Date:** 2026-05-20
**Updated:** 2026-07-14
**Deciders:** Project team

## Context

`micboard/manufacturers/` is a backward-compatibility shim layer. Its `__init__.py` (93 lines) dynamically mirrors `micboard.integrations.*` modules into `sys.modules` under the old `micboard.manufacturers` namespace.

The directory contains:
- `__init__.py` — module loader that patches sys.modules
- `base.py` (98 lines) — abstract base classes (`BaseAPIClient`, `BasePlugin`, `ManufacturerPlugin`)

The actual plugin implementations live in `micboard/integrations/shure/` and `micboard/integrations/sennheiser/`. The shim exists so that legacy import paths like `from micboard.manufacturers.shure import ...` continue to work.

Maintaining this shim:
- Creates confusion about the canonical import path.
- Uses dynamic sys.modules manipulation, which is fragile and hard to debug.
- Duplicates class definitions now owned by `micboard/services/common/base/`.
- Adds a maintenance burden for zero functional value.

## Decision

1. **Remove `micboard/manufacturers/` entirely** in a single PR.
2. **Update all import references** from `micboard.manufacturers.*` to `micboard.integrations.*`.
3. **Use the canonical contracts** in `micboard/services/common/base/`; do not create another
   shared hierarchy or compatibility export under `micboard/integrations/`.
4. **Remove all sys.modules patching logic** from the shim `__init__.py`.

## Consequences

- **Positive:** One fewer layer of indirection. Manufacturer implementations live under
  `integrations/`, while shared contracts have one source of truth under `services/common/base/`.
  About 100 lines of dead code were removed.
- **Negative:** Every file importing from `micboard.manufacturers` must be updated (estimate: 15-25 import sites). This must be coordinated to avoid breaking CI mid-migration.
- **Migration:** Single PR. No deprecation window — the shim has existed long enough that any actively maintained code paths should already be migrated. Verify by grepping for `micboard.manufacturers` across the entire repo.

## Compliance

- CI will fail if any file imports from `micboard.manufacturers`.
- Package initializers do not re-export plugin contracts or implementations.
