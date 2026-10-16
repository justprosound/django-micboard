---
title: "ADR-023: Performers, Events, and Time-bounded Assignments"
---
**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Project team

## Context

Performers change mics during Events, packs are swapped, and external planners schedule who
wears what. Assignments had no time window, performers had no tenant, and personal data was
unguarded. Decided in [#360](https://github.com/justprosound/django-micboard/issues/360), [#374](https://github.com/justprosound/django-micboard/issues/374), [#379](https://github.com/justprosound/django-micboard/issues/379), and [#380](https://github.com/justprosound/django-micboard/issues/380).

## Decision

1. A **Performer** belongs to one tenant. No identity is shared across tenants.
2. An **Event** has a location, a time window (optionally recurring), and a crew.
3. An **Assignment** has a half-open window `[start, end)`. Windows are closed and replaced,
   never edited, and a Postgres exclusion constraint forbids overlap on a unit. Operator
   overrides and grace periods keep a running show safe.
4. A **Handoff** closes one window and opens another, manually (including offline at the edge)
   or scheduled to an Event segment. A planner re-sync never reverts a live handoff.
5. `EventSource` providers (ICS, webhook or CSV, Planning Center) import planned windows
   idempotently.
6. Personal contact data is admin-only, its reads are audited, and it's purged after the
   tenant's retention period, with subject export and delete.

## Consequences

- History always answers who held a unit at any moment, so replay and post-Event reports are
  correct.

## Alternatives considered

- **Renaming the slot on a handoff:** rejected, because it destroys history.
- **Parsing handoffs from free-text notes:** rejected as fragile.
