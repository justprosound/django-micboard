---
title: "ADR-008: No compatibility layers"
description: "Why manufacturer code has one canonical import path and no re-export shims."
type: explanation
audience: developer
---

## Context

`micboard/manufacturers/` mirrored `micboard.integrations.*` into the old namespace by patching `sys.modules`, and duplicated base classes owned elsewhere. It created confusion about the canonical import path and cost maintenance for no functional value.

## Decision

- `micboard/manufacturers/` is removed. Manufacturer implementations live under `micboard/integrations/<code>/`, and shared contracts under `micboard/services/common/base/`.
- Package initializers do not re-export plugin contracts or implementations, and no compatibility module or alias exists. Call sites import from the defining module.
- The same rule applies elsewhere in the project: when an API moves or is removed, every call site changes in the same change.

## Consequences

One fewer layer of indirection and a single source of truth for each contract. Downstream code that imported the old namespace must switch to `micboard.integrations.*`.
