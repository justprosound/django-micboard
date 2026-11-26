---
title: "ADR-001: Services are small, single-purpose modules"
description: "Why the service layer is split by concern into focused modules."
type: explanation
audience: developer
---

## Context

The service layer had two outsized files, `discovery_service.py` (about 900 lines) and `hardware_lifecycle.py` (about 640), plus unused abstractions (`BaseCRUDService`, an empty `shared/utils.py`). Large mixed modules hid responsibility boundaries and made single concerns hard to test.

## Decision

- Services live in concern-named modules under `micboard/services/<domain>/`, each with one documented responsibility. Split by operational concern, not by arbitrary chunking, and keep files under about 400 lines (the guideline in `AGENTS.md`).
- Discovery is split across `micboard/services/sync/` into discovery, execution, trigger, queue, claim, approval, configuration, source-cursor and device-promotion modules. Hardware behavior is split across `services/core/` and `services/hardware/`.
- Unused abstract classes and placeholder modules are deleted, not kept. Callers import each owning module directly, with no re-export or compatibility module.

## Consequences

Each module is navigable and testable on its own, and the owning module for a behavior is predictable from its name. Moving or splitting a module means updating every call site in the same change.
