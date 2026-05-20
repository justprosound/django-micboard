# ADR-003: Admin Dashboard Modularization

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

`micboard/admin/dashboard.py` is 2,431 lines — the single largest file in the project. It contains approximately 50+ HTMX-powered views, inline formsets, JSON endpoints, tabular displays, and chart rendering for the custom Django admin dashboard.

This file handles multiple unrelated concerns:
- Chassis listing and detail views
- Wireless unit CRUD
- Charger display
- Manufacturer configuration
- Discovery queue approval
- Settings diff
- Monitoring views and alert management
- Gap analysis
- Bulk operations (import, export, assign)

A file of this size is:
- Impossible to review in a single PR.
- A merge-conflict magnet (every dashboard change touches this file).
- Hard to navigate (developers resort to text search rather than modular imports).
- A barrier to testing (no view in this file can be unit-tested in isolation).

## Decision

1. **Extract each major functional area into its own view module** under `micboard/admin/views/`:
   - `views/chassis.py` — chassis list, detail, inline management
   - `views/wireless_units.py` — unit CRUD, bulk operations
   - `views/discovery.py` — queue approval, device adoption
   - `views/chargers.py` — charger dashboard and slot management
   - `views/monitoring.py` — monitoring views and alert management
   - `views/config.py` — manufacturer configuration views
   - `views/settings.py` — settings diff and bulk config
   - `views/gap_analysis.py` — gap analysis views
2. **Keep `dashboard.py`** as the routing hub that imports and re-exports views from the submodules for backward compatibility, then remove re-exports after one release cycle.
3. **Each extracted view module** must be ≤400 lines. Any module exceeding this must be split further.

## Consequences

- **Positive:** Views become independently navigable, reviewable, and testable. Merge conflicts decrease. New developers can find the relevant view module instantly.
- **Negative:** Admin URL registration in `admin_urls.py` (597 lines) may need corresponding reorganization.
- **Migration:** Extract one area per PR, in dependency order (chassis first, since units and channels depend on it). Allocate 8-10 PRs.

## Compliance

- CI will enforce `micboard/admin/views/*.py` ≤400 lines.
