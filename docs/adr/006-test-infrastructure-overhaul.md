# ADR-006: Test Infrastructure Overhaul

**Status:** Proposed
**Date:** 2026-05-20
**Updated:** 2026-07-13
**Deciders:** (to be assigned)

## Implementation Status

Phases 1 through 3 were completed on 2026-07-13:

- Every installed concrete project model has a domain-grouped factory.
- A live registry contract detects missing and duplicate factory adapters.
- Each factory creates two independently valid, persisted instances and passes `full_clean()`.
- Core-only, optional multitenancy, and swappable-user host configurations are covered.
- Factory Boy remains outside the base runtime dependencies, and test support is excluded from
  wheels.
- Discovery, deduplication, hardware, location, performer, alert, connection, and uptime services
  have direct behavioral coverage at 90% or higher per targeted module.
- Query budgets protect discovery batching, alert fanout, connection health, and connection
  statistics from data-dependent query growth.
- Request-level smoke tests cover tenant-scoped chassis administration, atomic discovery approval,
  the monitoring dashboard, settings diffs, and HTMX channel fragments.

Phase 4 remains tracked by issue #71. CI currently enforces a synchronized 49% coverage floor; it
will be raised toward 60% and then 80% only as measured coverage supports those thresholds.

## Context

At the time of this decision, the test suite at `tests/` had 13 files (11 test modules plus
configuration). Coverage analysis showed:

- 33 of 38 service files have zero tests.
- No test factories exist (raw model instances constructed inline).
- No integration tests (service + model + DB).
- No E2E tests (admin views, HTMX flows, discovery pipeline).
- No fixture factories — tests construct model instances manually with inline kwargs.
- The flat `tests/` directory does not mirror the domain structure of the app.

This means:
- Service-layer changes have no automated safety net.
- Refactoring (ADR-001 through ADR-005) is high-risk without test coverage.
- CI provides no regression detection.

## Decision

1. **Adopt `factory_boy`** for model factories. Create one factory per model under `tests/factories/`.
2. **Restructure tests** from flat layout to domain-aligned:
   ```
   tests/
     conftest.py
     settings.py
     urls.py
     factories/
       __init__.py
       hardware.py
       discovery.py
       monitoring.py
       settings.py
       ...
     services/
       test_discovery_service.py
       test_hardware_service.py
       test_alert_service.py
       ...
     models/
       test_wireless_chassis.py
       test_rf_channel.py
       ...
     admin/
       test_dashboard_views.py
       ...
     integration/
       test_discovery_pipeline.py
       test_sync_lifecycle.py
       ...
   ```
3. **Target: service-layer coverage ≥80%** per module before refactoring. Write tests for every service method that has non-trivial branching.
4. **Add integration tests** for the discovery pipeline (scan → queue → adopt), sync lifecycle (poll → update → alert), and settings resolution chain.
5. **Add smoke/E2E tests** for critical admin flows using Django's test client (chassis CRUD, discovery approval, monitoring dashboard).

## Consequences

- **Positive:** Refactoring becomes safe. New contributors have visible patterns for writing tests. CI catches regressions. The factory layer reduces test boilerplate by ~70%.
- **Negative:** Adding ~300-400 tests requires dedicated sprints. Factory maintenance adds overhead when model schemas change.
- **Migration:** Phase 1 — factories for all models (complete). Phase 2 — service tests for
  discovery, hardware, monitoring domains (complete). Phase 3 — admin E2E smoke tests (complete).
  Phase 4 — integration pipeline tests.

## Compliance

- CI enforces the synchronized 49% coverage floor today, ratcheting to 60% and then 80% as the
  remaining phases add verified coverage.
- New service methods require tests in the same PR.
