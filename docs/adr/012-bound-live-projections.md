# ADR-012: Bound Live Monitoring Projections

**Status:** Implemented
**Date:** 2026-07-14
**Deciders:** Project team

## Context

Charger dashboards and display-wall kiosks are refreshed repeatedly through HTMX. Loading every
charger, slot, section, unit, and performer made memory and response size proportional to tenant
inventory. Tenant filtering prevented data disclosure but did not bound work inside a large
authorized tenant.

## Decision

1. Build live pages from primitive Pydantic snapshot DTOs rather than passing ORM graphs to
   templates.
2. Apply tenant visibility before every cutoff and use stable business ordering with primary-key
   tie breakers.
3. Enforce package ceilings:
   - charger dashboard: 64 chargers and 32 slots per charger;
   - display wall: 16 sections, 32 chargers per section, and 32 occupied slots per charger;
   - display-wall health: 16 sections, 32 chargers per section, and 32 slots per charger.
4. Fetch one sentinel row beyond each ceiling so snapshots can report truncation without counting
   the full relation.
5. Render accessible overflow notices from DTO truncation metadata.
6. Resolve performers and units only for identities present in the bounded visible window. When
   multiple active assignments exist, rank them in SQL and materialize only the winner for each
   unit, ordered by priority, update time, then primary key.

## Consequences

- Response memory, serialization, and template work have hard upper bounds.
- Query counts remain constant as inventory grows.
- Operators receive an explicit truncation notice instead of silently assuming a complete view.
- The live dashboard is a monitoring window, not an inventory export; complete inventory belongs
  in paginated administrative workflows.

## Compliance

- Query-budget tests cover empty and populated projections.
- Overflow and tenant-isolation tests prove filtering happens before truncation.
- New live projections must use typed DTOs, sentinel overflow detection, and a documented ceiling.
