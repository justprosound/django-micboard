# SRED Project Summary — 2026 Bound Live Monitoring Projections

<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

## Project Description

Charger dashboards and display-wall kiosks refreshed repeatedly through HTMX. Loading every charger, slot, section, unit, and performer made memory and response size proportional to tenant inventory. Tenant filtering prevented data disclosure but did not bound work inside a large authorized tenant. Query counts scaled with data volume, causing timeouts on large deployments.

## Project Goals

Build live pages from primitive Pydantic snapshot DTOs rather than passing ORM graphs to templates. Apply tenant visibility before every cutoff and use stable business ordering with primary-key tie breakers. Enforce package ceilings: charger dashboard (64 chargers, 32 slots/charger); display wall (16 sections, 32 chargers/section, 32 occupied slots/charger); display-wall health (16 sections, 32 chargers/section, 32 slots/charger). Fetch one sentinel row beyond each ceiling so snapshots report truncation without counting the full relation. Render accessible overflow notices from DTO truncation metadata. Resolve performers/units only for identities present in the bounded visible window; when multiple active assignments exist, rank in SQL and materialize only the winner per unit ordered by priority, update time, then primary key.

## Technical Uncertainties

### Uncertainty #1: Sentinel-Based Truncation Detection Without Full Count

**Description:** Needed to report "X more items" in UI without executing `COUNT(*)` on the full relation (defeats the bounding purpose). The challenge: detect truncation while fetching only ceiling+1 rows.

**Experiments:**
- Attempted: window function `ROW_NUMBER()` with `WHERE rn <= ceiling + 1` — worked but added query complexity
- Adopted: `queryset[:ceiling+1]` + Python-side `len(results) > ceiling` → `truncated = True`, `visible = results[:ceiling]`; ORM `LIMIT ceiling+1` is a single query

**Results / Learnings / Success:**
- Constant 1 query per projection regardless of tenant size
- Truncation metadata (`truncated=True`, `total_estimate="100+"`) in DTO for accessible notice
- Query-budget tests enforce constant query count for empty and 10K+ item tenants

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-012 Bound Live Monitoring Projections](../../adr/012-bound-live-projections.md)

### Uncertainty #2: Performer Assignment Resolution Within Bounded Window

**Description:** Multiple active `PerformerAssignment` records can exist for one `WirelessUnit` (handoffs, overlaps). In unbounded view, all were fetched. In bounded view, only assignments for units in the visible window should be resolved — but the "winning" assignment must be ranked globally, not just within the window.

**Experiments:**
- Subquery: `ROW_NUMBER() OVER (PARTITION BY unit_id ORDER BY priority DESC, updated_at DESC, pk)` in assignment CTE; join to units in visible window; filter `rn = 1`
- Single query returns units + their top-ranked performer; no post-processing

**Results / Learnings / Success:**
- Assignment resolution scales with window size (32), not inventory size (10,000)
- Global ranking preserved; window only limits materialization

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-012 Bound Live Monitoring Projections](../../adr/012-bound-live-projections.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / DTO Design | ~25% | Ceiling design, sentinel pattern, ADR-012 |
| (engineer) | Implementation / Query Budgets | ~35% | DTOs, projections, query-budget tests |
| (engineer) | Implementation / Overflow UI | ~25% | Accessible truncation notices, HTMX fragments |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-012 Bound Live Monitoring Projections](../../adr/012-bound-live-projections.md)
- [CONTEXT.md](../../development/context.md) (monitoring architecture)

**PRs:**
- (projection DTOs PR)
- (charger dashboard bounding PR)
- (display wall bounding PR)
- (query budget tests PR)
- (overflow UI PR)
