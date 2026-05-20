# ADR-002: Extract Business Logic from Models to Services

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

Several model classes in `micboard/models/` contain business logic embedded in `save()` overrides, `clean()` methods, and property methods:

- `WirelessChassis.save()` (~80 lines) — updates device status, triggers sync, manages network state transitions.
- `ManufacturerConfiguration.validate()` (~60 lines) — JSON schema validation and error collection.
- `DiscoveredDevice.save()` — duplicate detection and queue management.
- Several models use `post_save` signals that duplicate logic found in services.

This violates the single-responsibility principle. Models should define data structure, constraints, and query scope — not orchestrate side effects. Embedding business logic in models makes it:
- Impossible to test business rules without DB setup.
- Difficult to reuse logic outside model lifecycle (e.g., in bulk operations).
- Hard to reason about side-effect chains (save triggers signal triggers service).

## Decision

1. **Model `save()` methods must be idempotent and side-effect-free.** Remove all orchestration logic (sync triggers, status transitions, queue management) from `save()` overrides.
2. **Model `clean()` / `validate()` methods may keep structural validation** (field formats, required fields, uniqueness) but must not invoke services or write to DB.
3. **Existing post-save signal handlers** must be audited. If the logic duplicates a service method, remove the signal and call the service explicitly from the view/task layer instead.
4. **All business logic moves into domain services** under `micboard/services/<domain>/`. Service methods are the canonical way to perform multi-step operations involving models.

## Consequences

- **Positive:** Models become testable in isolation (no DB side effects). Business rules are reusable from views, tasks, and management commands alike. Side-effect chains are explicit in the caller.
- **Negative:** Existing callers that rely on implicit side-effects from `model.save()` will break. Each caller must be updated to invoke the corresponding service method.
- **Migration:** For each model, (a) introduce a service method encapsulating the side-effect, (b) update all call sites, (c) remove the `save()` override. Execute per-model in separate PRs.

## Compliance

- CI linting will flag any `save()` method overrides that contain DB writes, external calls, or signal emission.
