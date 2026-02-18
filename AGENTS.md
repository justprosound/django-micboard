# AGENTS.md — Agent & Assistant Coding Guide for django-micboard

This document distills all key architectural, workflow, and style rules for coded/automated contributions to the django-micboard project. Follow these guidelines to remain fully compliant with project policy, maximize code robustness, and enable seamless agentic development.

---

## Quick Reference — Agent Research
- **When you need to search docs, use `context7` tools.**
- **If you are unsure how to do something, use `gh_grep` to search code examples from GitHub.**

---

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
      uv venv .venv
      uv pip install -e ".[dev,all]"
      cp .env.example .env  # configure as needed
      ```
    - **WARNING:** You must use uv for ALL installation, management, and environment creation. Direct or indirect usage (even examples) of pip, pipx, venv, or poetry is strictly forbidden. Any environment setup, tool install, or dependency action must use uv to ensure reproducibility and security. If you see a non-uv pattern, report and fix instead of repeating or copying it.

- **Tests:**
    - Run all tests:
      ```bash
      pytest
      ```
    - Coverage:
      ```bash
      pytest --cov=micboard --cov-report=html
      ```
    - Markers (examples):
      - `pytest -m unit` (only unit tests)
      - `pytest -m integration` (integration tests)
      - `pytest -m django_db` (DB-required tests)
    - Specific test file:
      - `pytest tests/test_conf.py -v`

- **Linting/Autoformat:**
    - Check:
      ```bash
      ruff check .
      ```
    - Autoformat:
      ```bash
      ruff format .
      ```
    - Pre-commit (install and run all hooks):
      ```bash
      pre-commit install
      pre-commit run --all-files
      ```

- **Type Checking:**
    ```bash
    mypy micboard
    ```

- **Security:**
    ```bash
    bandit -r micboard -ll
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
- **Tasks** (async/Celery) wrap service logic for background execution only.
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

---

## 4. Logging, Error Handling, and Anti-Patterns

- Always use `logging.exception` in `except` blocks (never f-strings in logs). Example:
    ```python
    try:
        ...
    except Exception as exc:
        logger.exception("Operation failed for item %s", item_id)
    ```
- Never use bare `except:` blocks; always specify exceptions or catch `Exception`.
- Do not embed business logic into admin, tasks, or serializers—use services.
- Never create/maintain shims or legacy/compat modules. Remove old shims and update call sites to reference new modules directly.
- Avoid large catch-all utils files or modules with mixed unrelated responsibility.

---

## 5. Migrations (CRITICAL)

- Never edit, delete, or manually patch files in `micboard/migrations/`.
- Only generate new migrations when schema changes are absolutely required **and approved**.
- Always test migrations on clean and existing DBs using approved processes.
- All migration changes must be reviewed before merge.

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

---

## 8. Key References

- `.github/copilot-instructions.md` — canonical architecture and code rules
- `CONTRIBUTING.md`, `README.md` — contributor/dev workflow and policy
- `pyproject.toml` — all linter, type-checker, and test config
- `CHANGELOG.md`, `docs/` — history, architecture, and detailed APIs
- For full architecture, see `micboard/ARCHITECTURE.md`

---

**Agents: If in doubt, always check `.github/copilot-instructions.md` and follow the strictest pattern or ask for clarification via code review. No shims, no shortcuts, strict domain discipline!**
