---
title: "ADR-006: Factories, domain-aligned tests and a coverage floor"
description: "How the test suite is organized and what CI enforces."
type: explanation
audience: developer
---

## Context

The suite once had a handful of flat test files, no model factories and no integration coverage, so service-layer changes had no safety net and refactoring was risky.

## Decision

- Model factories use `factory_boy`, one factory module per domain under `tests/factories/`. `tests/test_factory_registry.py` checks that every installed concrete model has a factory adapter, so a new model without one fails the suite.
- Tests are grouped by domain (`tests/services/`, `tests/models/`, `tests/admin/`, `tests/tasks/`), with request-level smoke tests for the critical admin flows.
- Query budgets protect discovery batching, alert fanout and connection health from data-dependent query growth.
- CI enforces a 95% branch-coverage floor (`--cov-fail-under=95` in `.github/workflows/ci.yml`) and `scripts/check_coverage_inventory.py` rejects omitted distributable modules.
- New service methods ship with tests in the same pull request.

## Consequences

Refactoring is safe and contributors have visible patterns to follow. Factories need maintenance when model schemas change, and `factory-boy` stays a test-only dependency.
