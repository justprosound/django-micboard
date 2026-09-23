---
title: "ADR-012: Bound Live Monitoring Projections"
---
**Status:** Implemented
**Date:** 2026-07-14
**Deciders:** Project team
**Reviewed:** 2026-09-22

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

**Scope clarification (2026-09-22):** clauses 3 through 6 govern the unbounded live monitoring
windows — the charger dashboard, the display wall, and display-wall health — where a ceiling is
the only thing standing between inventory growth and an unbounded response. They do not govern
paginated administrative tables, whose page size already communicates the cutoff; the
Consequences below draw that line.

The one live surface that does not follow clause 1 is the performer-assignment refresh fragment
(`AssignmentRowsView` → `partials/assignment_rows.html`). It renders `PerformerAssignment` rows
with their related graph rather than a primitive snapshot DTO. It is bounded and deterministic —
visibility is applied before the 50-row slice, and the row query now ends in a primary-key
tie breaker — so it satisfies clause 2. Converting it to a snapshot DTO remains open work.

An earlier revision of this note claimed `unique_together` on
(`"performer", "wireless_unit"`) already made `("-priority", "performer", "wireless_unit")`
total. It does not: ordering by those relations sorts by their own `Meta.ordering`
(`Performer.name`, and `WirelessUnit.base_chassis__name, slot`), none of which is unique, so
distinct assignments could tie and cross the page boundary between refreshes.

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
