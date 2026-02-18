# Django Reusable App – GitHub Copilot Instructions

> **CRITICAL TOOLING POLICY**
>
> - All environments and dependency management must use [`uv`](https://github.com/astral-sh/uv) exclusively. Use of `pip`, `pipx`, `poetry`, or Python built-in `venv` is strictly forbidden. Any code, documentation, CI/CD, or script referencing non-`uv` patterns must be escalated and remediated immediately. See AGENTS.md and CONTRIBUTING.md for full enforcement/escalation details.
> - When searching documentation or code examples, always follow the agent quick reference below:
>   - Use `context7` tools for up-to-date documentation lookups.
>   - Use `gh_grep` to search for real code examples from public GitHub repositories.

These instructions define how GitHub Copilot must behave when assisting with this **Django reusable app** codebase.

Copilot should:

*   Prefer **existing patterns** and **project conventions** over inventing new ones.
*   Respect **global rules** in this file first, then follow **refactor‑specific guardrails**.
*   Assume this file is the **source of truth** for architecture, imports, and patterns.

If any suggestion would violate rules in this file, **Copilot must change the suggestion to comply**.

***

## 1. Global Architecture Overview

This repository contains a **Django reusable app** with a domain‑oriented, services‑based architecture. Copilot must:

*   Treat this as a **pluggable Django app** intended to be installed into a host project.
*   Avoid introducing assumptions about:
    *   Specific cloud platforms (e.g., Azure, AWS, GCP).
    *   Project‑level configuration (ROOT\_URLCONF, global settings, etc.), unless clearly present in this repo.

### High-level architecture

*   **Backend**
    *   Django (4.x or higher) with app code in `<app_name>/`
    *   Optional Celery tasks if present (see `<app_name>/tasks/` or similar)

*   **Frontend (if present)**
    *   Use existing frontend stack (e.g., Bootstrap, Tailwind, or other) as seen in the repo.
    *   Do **not** introduce a new frontend framework unless there is already a precedent.

*   **CI/CD & Tooling**
    *   Follow existing GitHub Actions or other pipeline patterns already in the repo.
    *   Pipelines typically handle linting, testing, and packaging for distribution (e.g., to PyPI).
    *   Copilot should **not** invent new deployment flows; use and extend existing patterns.

Copilot must keep new code, refactors, and examples consistent with this architecture.

***

## 2. Critical Developer Workflows

When suggesting commands or scripts, Copilot must align with the workflows defined in this repository. When unsure, it should **look for existing scripts and configs** and mirror their usage.

Examples (adapt if present):

*   **Local development**
    *   Prefer using existing `Makefile` targets, `nox` sessions, or documented commands in `README`/`CONTRIBUTING`.

*   **Tests**
    *   Use pytest with test settings:
        ```bash
        pytest
        ```
    *   If coverage is present:
        ```bash
        coverage run -m pytest
        ```

*   **Type checking** (if configured)
    *   For example:
        ```bash
        mypy <app_name>
        ```

*   **Background tasks (if Celery or similar is used)**
    *   Follow existing invocation patterns in the repo (e.g., `celery -A config.celery_app worker -l info`).
    *   Do not invent new entry points; copy existing conventions.

*   **Packaging**
    *   Respect existing build tooling (`pyproject.toml`, `setup.cfg`, `hatch`, `poetry`, etc.).
    *   Do not introduce a second, conflicting packaging system.

***

## 3. Global Project Conventions & Patterns

### 3.1 Naming

Copilot must follow these naming conventions:

*   Classes and class‑returning factory functions: `InitialCaps` (PascalCase)
*   Variables, functions, and methods: `snake_case`

### 3.2 Python Style

*   Use **4 spaces** for indentation.
*   Use **double quotes** for strings.
*   Assume tools such as **`ruff`**, **`isort`**, and **`black`** (or equivalent) are enforced.
*   **Never** suggest manual edits to Django migration files—generate new migrations instead (in the host project or this app, as applicable).

### 3.3 Logging

*   Use `logging.exception` for error logging in exception handlers.
*   Avoid f‑strings in log messages. Prefer:
    ```python
    logger.info("Processing item %s", item_id)
    ```

### 3.4 Caching

If this project uses caching, Copilot must apply the following rules:

*   Prefer **automatic ORM/database caching** if a tool like **django-cachalot** or equivalent is configured.

*   For DRF serializers/viewsets (if DRF is used):
    *   Rely on the project’s existing query caching behavior.
    *   **Do NOT** add redundant manual caching layers around ORM queries already handled by global caching.

*   Manual `django.core.cache` usage is allowed **only** for expensive non‑DB operations, such as:
    *   Thumbnail generation
    *   External API calls
    *   File I/O
    *   Complex calculations

*   Copilot should:
    *   Use **module‑level caches** for static or rarely changing resources when appropriate.
    *   Use **descriptive cache keys**, e.g.:
        ```python
        cache_key = f"thumbnail:{object_id}:{version}"
        ```
    *   Choose reasonable TTLs (typically 1–24 hours).
    *   Implement **cache invalidation** via signals or explicit hooks when underlying data changes.
    *   Avoid view‑level caching decorators unless there is already a project precedent.

### 3.5 Django Usage

*   Use idiomatic Django ORM patterns (e.g., `__icontains=self.q` for text search).
*   Maintain clear **model / service / view separation** consistent with existing patterns in `<app_name>/`.
*   Avoid circular imports; if a suggestion might cause a circular import, restructure the code (e.g., move logic into services).

### 3.6 DRF Throttling (If DRF is Used)

When working with Django REST Framework:

*   **Do NOT** set explicit `throttle_classes` on viewsets or views unless this is already a project-local pattern.
*   Prefer global throttling via DRF settings:
    *   `DEFAULT_THROTTLE_CLASSES`
    *   `DEFAULT_THROTTLE_RATES`

If different throttling is needed:

*   Adjust **global** DRF settings or clearly documented project-level configuration.
*   Avoid hard-coding throttle classes directly on views unless the repository already does so.

### 3.7 DRF Authentication (If DRF is Used)

*   Prefer the authentication scheme already used in the project:
    *   For example, if Django REST Knox is used:
        *   Ensure Knox’s `TokenAuthentication` comes **before** `SessionAuthentication` in `DEFAULT_AUTHENTICATION_CLASSES`.
    *   Do not introduce a different token scheme (e.g., DRF’s built‑in token auth) unless the project already uses it.

### 3.8 Frontend Guidelines (If Frontend Code Exists)

*   Do not introduce new UI frameworks; use whichever is already in the project (e.g., Bootstrap, Tailwind, etc.).
*   Prefer existing component patterns and CSS utility classes.
*   Keep UI changes minimal and consistent with current styling and structure.

### 3.9 Dependencies & Package Management

Copilot must **exclusively** use `uv` for all environment creation and dependency management in this project. The use of `pip`, `venv`, `pipx`, or `poetry` is **explicitly forbidden**. Any documentation, script, or config referencing these tools must be updated or escalated for correction. See AGENTS.md and CONTRIBUTING.md for remediation policy.

*   If dependencies are managed with **`uv`** and `requirements/`:
    *   Do **not** suggest manually editing compiled `requirements/*.txt` files.
    *   Instead:
        *   Edit the `.in` files (e.g., `requirements/base.in`).
        *   Then run:
            ```bash
            uv pip compile requirements/base.in -o requirements/base.txt
            uv pip install -r requirements/base.txt
            ```

*   If dependencies are managed via **`pyproject.toml`** and a tool like Poetry, Hatch, or PDM:
    *   (This pattern should not be used in this repository—see policy above.)

When adding optional dependencies, use the established extras or optional dependency mechanisms already in the project.

***

## 4. Integration Points

Copilot must preserve and respect existing integrations found in the repository. For example:

*   **Error tracking** (e.g., Sentry)
    *   DSN or credentials must come from environment/configuration.
    *   Never hard-code secrets.

*   **Email development tools** (e.g., MailHog)
    *   Respect local SMTP configs documented in `README` or settings.
    *   Do not hard-code host/ports beyond existing patterns.

*   **Background workers** (e.g., Celery, RQ, Django-Q2)
    *   Follow existing queue/task patterns for new background work.
    *   Do not introduce a second task queue framework.

*   **Authentication / authorization libraries**
    *   Extend or reuse existing integrations instead of introducing overlapping solutions.

***

## 5. Key Files & Directories

When suggesting new code or showing examples, Copilot should prefer these locations and patterns (adapted to this repo):

*   `<app_name>/` – Main Django app (models, services, admin, serializers, tasks, etc.).
*   `config/` or equivalent – Settings, Celery config, URLs (if present in this repo).
*   `requirements/` or `pyproject.toml` – Dependency definitions, if present.

Examples (for reference patterns; adjust to the actual repo):

*   **Celery tasks** – See `<app_name>/tasks.py` or `<app_name>/tasks/<domain>/tasks.py`.
*   **Admin customization** – See `<app_name>/admin/`.
*   **API views** – See `<app_name>/api_views.py` or `<app_name>/api/`.
*   **Custom filters** – See `<app_name>/filters.py`.

Copilot should **look at existing modules first** to mirror conventions.

***

## 6. Domain-Oriented Architecture & Refactor Guardrails

This project is migrating to a **domain‑based services architecture**.
These rules are **strict** and override any conflicting patterns elsewhere.

### 6.1 Absolutely No Shims or Compatibility Wrappers

Copilot must **never** generate or maintain:

*   Shim modules that pass through to new implementation locations.
*   “compat”, “legacy”, “bridge”, or alias modules providing old paths.
*   Re-export modules that hide actual implementation locations.

**Required behavior:**

*   Update **all call sites** to use the new domain modules directly.
*   Fix broken imports **at the call site**; do not create indirection layers.
*   Eliminate existing shims when discovered; route directly to the new APIs.

❌ **Forbidden example:**

```python
# Do NOT create compatibility wrappers like this:
# <app_name>/services/legacy/location.py
from <app_name>.services.location.services import LocationService

get_building_info = LocationService.get_building_info
```

✅ **Required pattern:**

```python
# In the calling file, update import directly:
from <app_name>.services.location.services import LocationService

result = LocationService.get_building_info(location_id)
```

If Copilot encounters a shim:

1.  Identify all usages.
2.  Replace call-site imports with direct imports to the new module.
3.  Remove the shim module.

***

### 6.2 No Giant Files (“God Modules”)

Copilot must:

*   Avoid creating files larger than **\~300–400 lines**.
*   Prefer splitting large, mixed‑concern files into smaller cohesive modules.
*   Maintain **single responsibility** per file where practical.

Common splitting patterns:

*   `services.py` →
    *   `services.py` (core business logic)
    *   `repository.py` (data access)
    *   `sync.py` (external sync logic)
    *   `dto.py` (data transfer objects)
    *   `validators.py` (validation rules)

*   `admin.py` →
    *   `admin.py` (primary ModelAdmin classes)
    *   `actions.py` (custom admin actions)
    *   `filters.py` (custom admin filters)
    *   `inlines.py` (admin inlines)

*   `tasks.py` →
    *   `tasks.py` (generic tasks)
    *   `sync_tasks.py` (sync-related tasks)
    *   `reporting_tasks.py` (reporting/analytics tasks)

When Copilot detects a large file with distinct responsibilities, it should **suggest and support splitting** along these lines.

***

### 6.3 Domain Folder Structure

All domain‑scoped logic should follow this structure:

```text
<app_name>/
  admin/<domain>/admin.py
  services/<domain>/services.py
  serializers/<domain>/serializers.py
  tasks/<domain>/tasks.py
```

Copilot should:

*   Infer domains from existing code and business responsibilities (e.g., `location`, `schedule`, `integrations`, `user`, `billing`, etc.).
*   Use **consistent domain names** across admin, services, serializers, tasks.
*   Ensure corresponding file structures and naming are aligned.
*   Avoid cross‑domain pollution (e.g., `location` services should not directly depend on `billing` internals).

***

### 6.4 Layer Responsibilities

Copilot must assign logic to the correct layer:

#### Admin Layer (`<app_name>/admin/<domain>/`)

*   Thin orchestration only.
*   Focus on Django admin configuration: `ModelAdmin`, filters, actions, inlines, UI integration.
*   Delegate business logic to **services**.
*   Preserve any existing integrations (e.g., custom admin mixins, search, permission tools).

#### Services Layer (`<app_name>/services/<domain>/`)

*   Owns **business operations** and domain workflows.
*   Defines **DTOs** (data transfer objects/simple containers).
*   Handles side effects:
    *   External API calls
    *   Sync operations
*   Enforces **domain boundaries** and high‑level validation.

#### Serializers Layer (`<app_name>/serializers/<domain>/`)

*   Handles input/output serialization and deserialization (for DRF or other layers).
*   Implements validation rules **specific to API contracts**.
*   Does **not** duplicate business logic; reuses services instead.

#### Tasks Layer (`<app_name>/tasks/<domain>/`)

*   Thin wrappers around domain services for background execution.
*   Uses the project’s standard task framework (Celery, Django-Q2, RQ, etc.).
*   Handles error logging/monitoring and retries, but delegates core behavior to services.

***

### 6.5 Django Integrations to Preserve During Refactors

When moving or refactoring code, Copilot must ensure any **existing integrations** remain functional, such as:

*   Search tools (e.g., django-watson or equivalents).
*   Advanced admin UI libraries.
*   Object-level permission libraries (e.g., django-guardian).
*   Background task schedulers (e.g., django-q2 or equivalents).
*   Debugging tools (e.g., django-debug-toolbar).

Rules:

*   Maintain existing integration behavior.
*   Update imports and configurations to match new domain paths.
*   Do not silently remove or break these integrations.

***

### 6.6 Workflow Constraints for Refactors

When Copilot helps with domain refactor work, it should:

*   **Touch all relevant layers** for a domain (admin, services, serializers, tasks) when reorganizing.
*   **Update all imports** so there are no broken references or dead modules.
*   Maintain **functional equivalence**: behavior must remain the same; only structure changes.
*   Ensure Django app loading and admin autodiscovery still work.

Refactor validation steps:

1.  Discover domains and determine correct boundaries.
2.  Organize files into domain subfolders.
3.  Move code to the correct domain modules.
4.  Update all imports and call sites (no shims).
5.  Verify integrations (admin, tasks, search, permissions, etc.).
6.  Remove obsolete files and indirection layers.

***

### 6.7 Forbidden Patterns (Refactor Context)

Copilot must **never** introduce or preserve:

#### Structural Anti‑patterns

*   Catch‑all `utils.py` files mixing unrelated helpers.
*   Modules with multiple unrelated responsibilities.
*   “Compatibility” layers that preserve old import paths.
*   Circular dependencies between domains.

#### Code Anti‑patterns

*   Business logic inside admin classes.
*   Duplicate service logic across layers or domains.
*   Large “god” modules that mix services, DTOs, sync, validation, repository, and tasks.
*   Bare `except:` blocks without specific exception handling.

#### Import Anti‑patterns

*   Shim modules that re‑export functions/classes.
*   Compatibility imports that wrap new modules.
*   Old import paths kept alive via indirection.
*   Constructs that cause circular import issues.

***

### 6.8 Quality Gates for Refactor Work

Before considering a refactor “done,” Copilot should ensure:

*   No shim modules remain.
*   File sizes are reasonable (ideally ≤ 300–400 lines).
*   All imports resolve and no circular dependencies are introduced.
*   Existing tests still pass after updates (tests updated as needed).
*   Integration behavior (admin, search, tasks, permissions, etc.) remains intact.
*   Functional behavior is preserved or improved; no regressions introduced.

***

## 7. Do / Don’t Summary

### 7.1 Do

*   ✅ Follow existing patterns for models, views, admin, services, serializers, and tasks.
*   ✅ Use existing local development, testing, and packaging workflows.
*   ✅ Reference `README`, `CONTRIBUTING`, and existing modules for canonical examples.
*   ✅ Use the project’s existing dependency management tooling (uv, Poetry, etc.).
*   ✅ Keep domain logic well‑structured and localized to domain folders.
*   ✅ Use services as the central place for business logic.

### 7.2 Don’t

*   ❌ Don’t edit compiled dependency files (e.g., `requirements/*.txt`) directly if they are generated.
*   ❌ Don’t edit migration files manually.
*   ❌ Don’t add redundant caching layers around DB queries already handled by existing caching tools.
*   ❌ Don’t introduce per‑view throttle classes unless that’s an established pattern.
*   ❌ Don’t introduce shims, compatibility wrappers, or alias modules.
*   ❌ Don’t create large, mixed‑concern modules instead of splitting by responsibility.
*   ❌ Don’t embed business logic in admin or tasks; use services instead.
