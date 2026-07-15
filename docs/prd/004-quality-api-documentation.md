# PRD-004: Quality, API, and Documentation

**Status:** In Progress
**Date:** 2026-05-20
**Updated:** 2026-07-14

## Problem Statement

The project originally lacked factories, integration coverage, and an enforced coverage gate. Those
quality foundations are now implemented: the distributable package is covered by a 95% branch
floor, discovery and poll-to-alert integration paths are exercised, critical admin workflows have
request-level coverage, and the plugin development contract is documented. The read-only v1 REST
API remains a separate outstanding deliverable.

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
- **Coverage target:** `just coverage` enforces at least 95% branch coverage and checks that every
  distributable Python module is included.
- **API v1:** DRF ViewSets at `micboard/api/v1/` with GET-only endpoints for chassis, wireless units, RF channels, discovery status, monitoring state, and settings. Read-only avoids write-side validation complexity.
- **CI gates:** pre-commit hooks run formatting, lint, typing, migration, and documentation
  integrity checks. GitHub Actions additionally run coverage and Bandit security scans on every PR.

## Success Metrics

- `just coverage` passes with at least 95% branch coverage.
- Integration tests for discovery pipeline and sync lifecycle.
- Admin E2E tests for 5 critical flows (chassis CRUD, discovery approval, monitoring).
- API v1 serves GET endpoints for core models with DRF browsable docs.
- Pre-commit hooks block lint/type/security violations before commit.
- Plugin development guide exists at `docs/plugin-development.md`.

## Risks

- **Coverage theater:** Enforcing coverage thresholds without meaningful assertions. Mitigate by requiring integration tests alongside unit tests.
- **Factory maintenance:** Model schema changes require factory updates — must be part of PR checklist.
- **API surface creep:** Read-only v1 may tempt premature write endpoint addition. Enforce scope in code review.

## Issues

- #69 — factory catalog (implemented)
- #70 — service-layer coverage (implemented)
- #71 — discovery and sync integration coverage (implemented)
- #72 — admin workflow coverage (implemented)
- #73 — pre-commit and CI quality gates (implemented)
- #74 — read-only v1 REST API (outstanding)
- #75 — plugin development guide (implemented)

## References

- ADR-006: Test Infrastructure Overhaul
- ADR-007: Introduce DRF API Layer with Versioning
