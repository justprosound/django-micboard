# PRD-004: Quality, API, and Documentation

**Status:** Proposed
**Date:** 2026-05-20

## Problem Statement

django-micboard has no automated test safety net — 33 of 38 service files are untested, no factories exist, and no integration or E2E tests run in CI. There is no REST API for programmatic access, and API documentation is absent. CI quality pipelines (linting, type checking, security scanning) run but lack coverage gates.

## Goals

1. Establish test infrastructure (factory_boy, domain-aligned test layout).
2. Achieve ≥80% service-layer test coverage for discovery, hardware, and monitoring domains.
3. Add integration tests for the discovery pipeline and sync lifecycle.
4. Add E2E smoke tests for 5 critical admin flows.
5. Introduce a v1 REST API (read-only) using DRF.
6. Configure pre-commit hooks and CI quality gates.
7. Document plugin development process.

## Non-Goals

- Reaching 100% test coverage across the entire codebase.
- Adding write endpoints to the API (v1 is read-only).
- Building a new frontend or deprecating admin views.

## Scope

| Area | ADR | Issues |
|------|-----|--------|
| Test factories | ADR-006 | #69 |
| Service-layer tests | ADR-006 | #70 |
| Integration tests | ADR-006 | #71 |
| Admin E2E smoke tests | ADR-006 | #72 |
| CI quality config | — | #73 |
| v1 REST API | ADR-007 | #74 |
| Plugin development guide | — | #75 |

## Design

- **Factories:** One `factory_boy` factory per model under `tests/factories/`. Inline model construction is replaced across all existing tests.
- **Test structure:** Restructure from flat `tests/` to domain-aligned: `tests/services/`, `tests/models/`, `tests/admin/`, `tests/integration/`.
- **Coverage targets:** `pytest --cov=micboard --cov-fail-under=60` initially, stepping to 80%.
- **API v1:** DRF ViewSets at `micboard/api/v1/` with GET-only endpoints for chassis, wireless units, RF channels, discovery status, monitoring state, and settings. Read-only avoids write-side validation complexity.
- **CI gates:** pre-commit hooks (ruff, mypy, bandit). GitHub Actions run lint, type-check, test (with coverage), and security scan on every PR.

## Success Metrics

- `pytest --cov=micboard --cov-fail-under=60` passes.
- Integration tests for discovery pipeline and sync lifecycle.
- Admin E2E tests for 5 critical flows (chassis CRUD, discovery approval, monitoring).
- API v1 serves GET endpoints for core models with DRF browsable docs.
- Pre-commit hooks block lint/type/security violations before commit.
- Plugin development guide exists at `docs/guides/plugin-development.md`.

## Risks

- **Coverage theater:** Enforcing coverage thresholds without meaningful assertions. Mitigate by requiring integration tests alongside unit tests.
- **Factory maintenance:** Model schema changes require factory updates — must be part of PR checklist.
- **API surface creep:** Read-only v1 may tempt premature write endpoint addition. Enforce scope in code review.

## Issues

- #69 — test: add factory_boy factories for all models
- #70 — test: write service-level tests for discovery, hardware, and monitoring
- #71 — test: write integration tests for discovery pipeline and sync lifecycle
- #72 — test: write admin E2E smoke tests for 5 critical flows
- #73 — chore: configure pre-commit hooks and CI quality jobs
- #74 — feat: implement v1 REST API with DRF (read-only, core models)
- #75 — docs: create plugin development guide

## References

- ADR-006: Test Infrastructure Overhaul
- ADR-007: Introduce DRF API Layer with Versioning
