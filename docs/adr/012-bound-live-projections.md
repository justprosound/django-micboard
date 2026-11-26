---
title: "ADR-012: Bound live monitoring projections"
description: "Why charger dashboards and display walls build from bounded snapshots."
type: explanation
audience: developer
---

## Context

Charger dashboards and display-wall kiosks refresh repeatedly through HTMX. Loading every charger, slot, unit and performer made memory and response size proportional to tenant inventory. Tenant filtering prevented disclosure but not unbounded work inside a large tenant.

## Decision

- Live pages are built from primitive Pydantic snapshot DTOs, not ORM graphs.
- Tenant visibility applies before any cutoff, with stable ordering and a primary-key tie breaker.
- Hard ceilings: the charger dashboard shows 64 chargers and 32 slots per charger (`services/chargers/dashboard_dtos.py`). The display wall shows 16 sections, 32 chargers per section and 32 occupied slots per charger (`services/kiosk/dtos.py`).
- One sentinel row past each ceiling lets a snapshot report truncation without counting the whole relation, and the page renders an accessible overflow notice.
- Performers and units are resolved only for the visible window. Where several active assignments exist, SQL ranks them and only the winner per unit is loaded.
- Paginated admin tables are exempt: their page size already communicates the cutoff.

## Consequences

Memory, serialization and template work have hard upper bounds, and query counts stay constant as inventory grows. The live dashboard is a monitoring window, not an inventory export. New live projections need typed DTOs, sentinel overflow detection, a documented ceiling and query-budget tests.
