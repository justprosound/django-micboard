<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Test Infrastructure Overhaul

## Project Description

At project start, the test suite had 13 files (11 test modules + config). Coverage analysis revealed: 33 of 38 service files had zero tests; no test factories existed (raw model instances constructed inline); no integration tests (service + model + DB); no E2E tests (admin views, HTMX flows, discovery pipeline); no fixture factories; flat `tests/` directory not mirroring domain structure. Branch coverage was unmeasured.

## Project Goals

Build factory-based test infrastructure from zero to 95% branch-coverage floor across all distributable Python modules. Domain-grouped factories with live registry contract detecting missing/duplicate adapters. Each factory creates two independently valid, persisted instances passing `full_clean()`. Cover core-only, optional multitenancy, and swappable-user host configurations. Direct behavioral coverage ≥90% per targeted service module. Query budgets protect discovery batching, alert fanout, connection health, and connection statistics from data-dependent query growth. Request-level smoke tests cover tenant-scoped chassis admin, atomic discovery approval, monitoring dashboard, settings diffs, HTMX channel fragments. Exclude Factory Boy from base runtime dependencies; test support excluded from wheels.

## Technical Uncertainties

### Uncertainty #1: Factory Registry Contract — Detecting Missing/Duplicate Adapters at Import Time

**Description:** With ~50 models across 10 domains, manually maintaining factory registration was error-prone. Missing factories would silently fall back to inline construction; duplicate factories would cause subtle test pollution.

**Experiments:**
- Spike: metaclass-based auto-registration — opaque, hard to debug
- Spike: explicit registry dict in `tests/factories/__init__.py` — required manual sync
- Adopted: live registry contract in `tests/factories/registry.py` — scans `tests/factories/` at import, builds domain→model→factory map, asserts every concrete model has exactly one factory adapter, fails fast in CI with actionable error listing missing/duplicate models

**Results / Learnings / Success:**
- 0 missing factories; 0 duplicates across 50+ models
- New model → add factory file → CI passes; no registry maintenance
- Contract test runs in <200ms; part of every test invocation

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md)
- **Code:** `tests/factories/registry.py`

### Uncertainty #2: Query Budgets for Data-Dependent Operations

**Description:** Discovery batching, alert fanout, connection health, and connection statistics queries scaled with tenant inventory size. No existing mechanism to enforce constant query count regardless of data volume.

**Experiments:**
- Attempted: `django-test-utils` query counting — too coarse, counted framework queries
- Adopted: custom `QueryBudget` context manager wrapping `django.db.connection.queries` with domain-specific allowances; integrated into service tests as `with QueryBudget(discovery_batch=5): service.run()`; CI fails if exceeded

**Results / Learnings / Success:**
- Discovery batching: 5 queries regardless of 10 or 10,000 devices
- Alert fanout: 3 queries regardless of 100 or 10,000 performers
- Connection health: 2 queries per check
- Budgets documented in test files; serve as living performance contracts

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md)

### Uncertainty #3: Factory Boy Outside Runtime Dependencies

**Description:** Factory Boy is a test-only dependency. Including it in base `pyproject.toml` would ship it to all consumers. Excluding it meant test environment couldn't import factories without manual install.

**Experiments:**
- Attempted: `[test]` extra with factory-boy — consumers had to `pip install django-micboard[test]`
- Adopted: Factory Boy in `tests/requirements.txt` (dev-only); test runner script installs it via `uv pip install -r tests/requirements.txt`; base wheel has no test deps; CI uses `uv sync --all-extras` for test environment

**Results / Learnings / Success:**
- Clean separation: runtime wheel has zero test dependencies
- Developers get full factory support via `uv sync --all-extras`
- No accidental test-only imports in runtime code (enforced by `import-linter`)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md)
- **Config:** `tests/requirements.txt`, `pyproject.toml` extras

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / Framework | ~30% | Registry contract, query budget design, ADR-006 |
| (engineer) | Factory Implementation | ~40% | 50+ domain factories, domain-grouped structure |
| (engineer) | Service Tests / Smoke Tests | ~35% | Behavioral coverage, HTMX smoke tests, CI integration |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-006 Test Infrastructure Overhaul](../../adr/006-test-infrastructure-overhaul.md)
- [CONTEXT.md](../../development/context.md) (testing strategy section)

**PRs:**
- (factory registry PR)
- (domain factories PRs per domain)
- (service behavioral tests PRs)
- (query budget PR)
- (smoke test framework PR)
- (CI enforcement PR)
