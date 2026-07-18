# SRED Project Summary — 2026 Admin Dashboard Modularization

<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

## Project Description

`micboard/admin/dashboard.py` was 2,431 lines — the single largest file in the project. It contained 50+ HTMX-powered views, inline formsets, JSON endpoints, tabular displays, and chart rendering for chassis management, wireless unit CRUD, charger display, manufacturer configuration, discovery queue approval, settings diff, monitoring, and gap analysis. All concerns were mixed in one module. The dashboard overview and gap analysis views were never registered but remained as latent global data exposures.

## Project Goals

Extract each major functional area into its own admin module under `micboard/admin/` following the existing domain-based pattern. Remove unregistered/reachable views entirely (no compatibility shims). Ensure each module is independently navigable, testable, and domain-owned. Target: no admin module >400 lines.

## Technical Uncertainties

### Uncertainty #1: Identifying Reachable vs Dead Code in a 2,431-Line Monolith

**Description:** The dashboard contained views for concerns that were never routed or registered (dashboard overview, gap analysis). Retaining them would preserve global unscoped data views as security hazards. No automated tooling existed to distinguish reachable admin surface from dead code.

**Experiments:**
- Static analysis: grep for `@admin.register`, `admin.site.register`, URLconf includes — only 6 of 50+ view classes were actually registered
- Runtime: added middleware to log admin view access in staging — confirmed 44 views never hit in 30 days
- Decision: remove unregistered views entirely in cleanup phase (2026-07-14); no deprecation window

**Results / Learnings / Success:**
- 2,431 lines → 8 domain modules (largest: `receivers.py` 400L, `configuration.py` 240L)
- Dead code removal eliminated latent security surface
- Merge conflicts on admin reduced to near-zero

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-003 Admin Dashboard Modularization](../../adr/003-admin-dashboard-modularization.md)

### Uncertainty #2: Preserving HTMX Fragment Contracts Across Module Boundaries

**Description:** HTMX views returned HTML fragments with specific DOM structure expected by frontend JavaScript. Moving views to domain modules risked breaking fragment contracts (CSS classes, element IDs, event names) without a test harness to detect regressions.

**Experiments:**
- Extracted views to domain modules with identical method signatures and template paths
- Added request-level smoke tests for each HTMX endpoint (tenant-scoped chassis admin, atomic discovery approval, monitoring dashboard, settings diffs, HTMX channel fragments)
- CI runs smoke tests against live Django test server with HTMX client simulation

**Results / Learnings / Success:**
- All HTMX contracts preserved; smoke tests catch DOM regressions
- Fragment templates remain in original locations (`templates/admin/micboard/...`) — only view logic moved

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-003 Admin Dashboard Modularization](../../adr/003-admin-dashboard-modularization.md)
- **Related:** [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md) (smoke test framework)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Spike | ~20% | Reachability analysis, module boundary design |
| (engineer) | Implementation / Testing | ~40% | View extraction, smoke test implementation |
| (engineer) | Implementation | ~25% | Template preservation, cleanup phase |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-003 Admin Dashboard Modularization](../../adr/003-admin-dashboard-modularization.md)
- [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md)

**PRs:**
- (main extraction PR)
- (dead code removal PR: dashboard overview, gap analysis, templates, DTOs, tests)
