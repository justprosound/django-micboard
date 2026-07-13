# ADR-006: Test Infrastructure Overhaul

**Status:** Proposed
**Date:** 2026-05-20
**Deciders:** (to be assigned)

## Context

The test suite at `tests/` has 13 files (11 test modules + conftest + settings + urls). Coverage analysis shows:

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
       hardware_factories.py
       discovery_factories.py
       monitoring_factories.py
       settings_factories.py
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
- **Migration:** Phase 1 — factories for all models. Phase 2 — service tests for discovery, hardware, monitoring domains. Phase 3 — admin E2E smoke tests. Phase 4 — integration pipeline tests.

## Compliance

- CI will enforce `uv run pytest --cov=micboard --cov-fail-under=60` initially, stepping to 80% over time.
- New service methods require tests in the same PR.
