# AGENTS.md — Agent & Assistant Coding Guide for django-micboard

This document distills all key architectural, workflow, and style rules for coded/automated contributions to the django-micboard project. Follow these guidelines to remain fully compliant with project policy, maximize code robustness, and enable seamless agentic development.

---



## Persistent Skills

- `caveman` - Ultra-compressed communication mode
- `pirate-skill` - Speak like a pirate
- `django-access-review` - Django access control and IDOR security review
- `django-drf` - Django REST Framework guidance
- `django-patterns` - Django architecture patterns, REST API design with DRF, ORM best practices, caching, signals, middleware, and production-grade Django apps
- `django-perf-review` - Django performance code review
- `django-security` - Django security best practices, authentication, authorization, CSRF protection, SQL injection prevention, XSS prevention, and secure deployment configurations
- `django-verification` - Verification loop for Django projects: migrations, linting, tests with coverage, security scans, and deployment readiness checks before release or PR

## Quick Reference — Agent Research
- **When you need to search docs, use `context7` tools.**
- **If you are unsure how to do something, use `gh_grep` to search code examples from GitHub.**

---

## Architectural Standards

### 1. Service Layer Pattern
- **Logic Isolation**: Business logic MUST reside in the Service Layer. Django management commands and views should be "thin wrappers".
- **Service Structure**: Use `DefaultsService`, `UpsertService`, and `BulkPersistService` patterns.

### 2. Data Transfer Objects (DTOs)
- **Standardization**: Use DTOs for data passing; **Pydantic (v2)** is mandatory.
- **Base Class**: Inherit from `PydanticBaseDTO` for standard config.
- **Mapping**: Use `DTOMapper` for type-safe Django model to DTO conversion.

### 3. Type Safety
- **Type Hints**: Required for all public methods and service/DTO definitions.

## 1. Local Build, Test, Lint, Type, and Security Commands

> **CRITICAL: uv IS MANDATORY**
>
> All agents and developers MUST use `uv` for all dependency installation and environment management in every context. Do **NOT** use `pip`, `pipx`, `poetry`, or Python's built-in `venv` directly—this is MANDATORY for reproducibility, security, and agent workflow support.
>
> **Resilience and Enforcement Policy:**
> - If any documentation, code, PR, CI/CD config, script, or troubleshooting advice in this project (or a dependency) references or recommends `pip`, `pipx`, `poetry`, or direct `venv` usage, you must:
>   1. IMMEDIATELY halt and do NOT proceed with that setup or change!
>   2. Notify the maintainers and update the offending documentation/code to use `uv` exclusively.
>   3. PR reviewers must BLOCK any contributions that introduce, re-enable, or suggest legacy/non-uv patterns (even in troubleshooting, migration notes, and comments).
>   4. Agents and automation MUST refuse to reproduce or propagate bad patterns—raise an error instead.
>
> **If you are unsure, STOP and escalate to maintainers before proceeding.**
>
> To enforce this at the tooling level, a `uv-check` must be included in every installing or running script. See Justfile for the canonical enforcement example.

- **Setup & Install:**
    - Clone and set up the development environment (using uv ONLY; all others strictly forbidden):
      ```bash
      git clone https://github.com/justprosound/django-micboard.git
      cd django-micboard
      uv sync --locked --all-extras
      cp .env.example .env  # configure as needed
      ```
    - **WARNING:** You must use uv for ALL installation, management, and environment creation. Direct or indirect usage (even examples) of pip, pipx, venv, or poetry is strictly forbidden. Any environment setup, tool install, or dependency action must use uv to ensure reproducibility and security. If you see a non-uv pattern, report and fix instead of repeating or copying it.

- **Tests:**
    - Run all tests:
      ```bash
      uv run --no-sync pytest
      ```
    - Coverage:
      ```bash
      uv run --no-sync pytest --cov=micboard --cov-report=html
      ```
    - Markers (examples):
      - `uv run --no-sync pytest -m unit` (only unit tests)
      - `uv run --no-sync pytest -m integration` (integration tests)
      - `uv run --no-sync pytest -m django_db` (DB-required tests)
    - Specific test file:
      - `uv run --no-sync pytest tests/test_settings_service.py -v`

- **Linting/Autoformat:**
    - Check:
      ```bash
      uv run --no-sync ruff check .
      ```
    - Autoformat:
      ```bash
      uv run --no-sync ruff format .
      ```
    - Pre-commit (install and run all hooks):
      ```bash
      uv run --no-sync pre-commit install
      uv run --no-sync pre-commit run --all-files
      ```

- **Type Checking:**
    ```bash
    uv run --no-sync python -m mypy micboard
    ```

- **Security:**
    ```bash
    uv run --no-sync bandit -r micboard -ll
    ```

---

## 2. Directory Structure & Domain Architecture

- All code is grouped by business domain:
    ```
    micboard/services/<domain>/services.py
    micboard/tasks/<domain>/tasks.py
    micboard/serializers/<domain>/serializers.py
    micboard/admin/<domain>/admin.py
    micboard/api/<domain>/views.py
    ```
- No files should exceed ~300–400 lines. Split by responsibility (see copilot-instructions.md for split patterns).
- **Services** own business logic (use DTOs, orchestrate high-level behavior).
- **Tasks** (async/Huey) wrap service logic for background execution only. Celery and django-q2 are **LEGACY**.
- **Admin** and **Serializers** are thin and never contain business logic.
- Tests reside in the `tests/` root-level folder or in domain-specific test files.

---

## 3. Code Style: Imports, Quotes, Indentation, Naming

- **Imports order:**
    1. `__future__` imports
    2. Python standard lib
    3. Django imports
    4. Third-party
    5. First-party (micboard)
    6. Relative/local
    - Enforced by ruff/isort with `pyproject.toml` settings

- **String quotes:** Always use double quotes.
- **Indentation:** 4 spaces everywhere (no tabs).
- **Line length:** 100 chars (ruff).
- **Class names:** `PascalCase` (InitialCaps).
- **Functions/variables:** `snake_case`.
- **Type hints:** Required for all public functions.
- **HTTP Client**: Use **`httpx`** for modern, async-compatible requests. **`requests`** is deprecated for new development.

---

## 4. Logging, Error Handling, and Anti-Patterns

- Always use `logging.exception` in `except` blocks. F-strings are preferred for readability. Example:
    ```python
    try:
        ...
    except Exception as exc:
        logger.exception(f"Operation failed for item {item_id}")
    ```
- Never use bare `except:` blocks; always specify exceptions or catch `Exception`.
- Do not embed business logic into admin, tasks, or serializers—use services.
- Never create/maintain shims or legacy/compat modules. Remove old shims and update call sites to reference new modules directly.
- Avoid large catch-all utils files or modules with mixed unrelated responsibility.
- **Task Queue**: All background work must use native **Huey** through `huey.contrib.djhuey`. Celery and django-q2 are deprecated.

---

## 5. Migrations (CRITICAL)

- Never edit, delete, or manually patch files in `micboard/migrations/`.
- Only generate new migrations when schema changes are absolutely required **and approved**.
- Always test migrations on clean and existing DBs using approved processes.
- All migration changes must be reviewed before merge.
- Use **`django-safemigrate`** for all production migrations.

---

## 6. PRs, Documentation, and Changelog

- Always add/update:
    - Docstrings and type hints for all public functions/classes
    - CHANGELOG.md (under `[Unreleased]` section)
    - README.md if user-facing changes
- PRs are committed by feature branch with a conventional commit style (e.g., `feat:`, `fix:`, etc.). See CONTRIBUTING.md for format.
- All code must pass CI checks before merge: ruff, mypy, pytest, bandit, pre-commit.

---

## 7. Forbidden Patterns and Agent Guardrails

- **Never:**
    - Suggest/retain shims, legacy re-exports, or compat/alias modules
    - Circumvent architectural organization (always follow domain split)
    - Mix business logic across domains/layers
    - Modify or delete existing migration files
    - Edit compiled requirements files directly (edit `.in` or pyproject.toml only)
    - Introduce new frameworks, caching, or queue solutions unless a precedent exists
- **Always:**
    - Place all core logic in domain services
    - Update ALL references when removing/shifting APIs (no backward-compat wrappers)
    - Follow all guidelines in `.github/copilot-instructions.md` as absolute authority
    - Standardize on the documented project stack (native Huey, httpx, pydantic, tenacity, etc.)

---

## 8. Key References

- `.github/copilot-instructions.md` — canonical architecture and code rules
- `CONTRIBUTING.md`, `README.md` — contributor/dev workflow and policy
- `pyproject.toml` — all linter, type-checker, and test config
- `CHANGELOG.md`, `docs/` — history, architecture, and detailed APIs
- For full architecture, see `micboard/ARCHITECTURE.md`

---

**Agents: If in doubt, always check `.github/copilot-instructions.md` and follow the strictest pattern or ask for clarification via code review. No shims, no shortcuts, strict domain discipline!

---

## Agent skills

### Required skills

The following skills are always loaded:
- **caveman** — ultra-compressed communication mode
- **pirate-skill** — speak like a pirate

### Auto-enablement

Additional skills listed in `available_skills` are loaded dynamically as they become relevant to the task at hand.

### Issue tracker

Issues are tracked as GitHub issues on this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels use their default names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/` at root). See `docs/agents/domain.md`.
