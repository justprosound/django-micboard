# PRD-002: Admin Modernization

**Status:** Proposed
**Date:** 2026-05-20

## Problem Statement

`micboard/admin/dashboard.py` is 2,431 lines — the single largest file in the project. It contains ~50+ HTMX views spanning chassis management, wireless unit CRUD, charger display, discovery queue approval, manufacturer configuration, settings diff, monitoring, and gap analysis. This monolith creates merge conflicts, blocks independent review, and prevents isolated testing.

## Goals

1. Split dashboard.py into per-domain view modules at `micboard/admin/views/`.
2. Each extracted module ≤400 lines with a single functional responsibility.
3. Reorganize `admin_urls.py` (597 lines) to match the new module structure.

## Non-Goals

- Changing view behavior or business logic.
- Rewriting HTMX templates or frontend code.
- Introducing a new admin UI framework.

## Scope

| Area | ADR | Issues |
|------|-----|--------|
| Extract chassis views | ADR-003 | #57 |
| Extract wireless unit views | ADR-003 | #58 |
| Extract discovery queue and charger views | ADR-003 | #59 |
| Extract monitoring and config views | ADR-003 | #60 |
| Extract settings and gap analysis views | ADR-003 | #61 |
| Reorganize admin URL config | ADR-003 | #62 |

## Design

- **Extraction pattern:** One PR per domain module. Each PR moves the relevant view classes/functions into `micboard/admin/views/<domain>.py`. The original `dashboard.py` imports and re-exports from the new module for backward compatibility.
- **URL reorganization:** `admin_urls.py` splits into `micboard/admin/urls/` with per-domain URL modules, keyed from a central `admin/urls/__init__.py`.
- **Deprecation window:** Dashboard re-exports maintained for one release cycle, then removed.

## Success Metrics

- dashboard.py reduces from 2,431 lines to a routing hub (<100 lines).
- Each `micboard/admin/views/*.py` ≤400 lines.
- All existing URL names resolve correctly.
- `ruff check .` and `pytest` pass.

## Risks

- **Merge conflicts:** Extract in dependency order (chassis first) to minimize conflicts.
- **URL name collisions:** Each submodule must namespace its URL names to avoid clashes.
- **Backward compatibility:** Any code importing views from `admin.dashboard` will break after the deprecation window — must coordinate with consumers.

## Issues

- #57 — refactor: extract chassis views from admin/dashboard.py
- #58 — refactor: extract wireless unit views from admin/dashboard.py
- #59 — refactor: extract discovery queue and charger views
- #60 — refactor: extract monitoring and configuration views
- #61 — refactor: extract settings and gap analysis views
- #62 — refactor: reorganize admin_urls.py

## References

- ADR-003: Admin Dashboard Modularization
