---
name: django-architecture
description: Review Django code for project-specific domain architecture compliance
allowed-tools: Read Grep Glob
---

Review changed Python code against django-micboard's domain architecture rules.

## Domain Architecture Rules

1. **Service Layer owns business logic** — `micboard/services/<domain>/services.py` owns all business operations. Admin, tasks, and serializers must NOT contain business logic — they delegate to services.

2. **Domain separation** — Code must follow `micboard/services/<domain>/`, `micboard/admin/<domain>/`, `micboard/tasks/<domain>/`, `micboard/serializers/<domain>/` structure. Cross-domain pollution (e.g., `location` services depending on `billing` internals) is forbidden.

3. **No shim/compat modules** — Never create backward-compat wrappers, alias modules, or re-exports that preserve old import paths. Update call sites directly.

4. **File size limit** — No file should exceed ~300-400 lines. If a file grows beyond, it must be split by responsibility (services.py -> services.py + repository.py + dto.py + validators.py).

5. **No god modules** — Catch-all `utils.py` or modules with mixed unrelated responsibilities are forbidden.

6. **No business logic in admin** — Admin classes (`ModelAdmin`, filters, actions, inlines) must be thin orchestration only. Delegate to services.

7. **No business logic in tasks** — Celery tasks are thin wrappers around service methods. Error handling and retries live in the task layer but core behavior delegates to services.

8. **No business logic in serializers** — Serializers handle I/O formatting and API-contract validation. Business rules go in services.

## Django-Specific Rules

9. **Migration immutability** — Never edit, delete, or manually patch files in `micboard/migrations/`. Only generate new migrations via `makemigrations`.

10. **Uv-only dependency management** — ALL environment and package management uses `uv`. No `pip`, `pipx`, `poetry`, or `venv` usage allowed in any code, docs, or scripts.

11. **String quotes** — Always use double quotes for Python strings.

12. **Logging** — Use `logging.exception` in `except` blocks with f-strings. Never bare `except:`.

13. **Imports order** — `__future__` -> stdlib -> Django -> third-party -> first-party (`micboard`) -> local.

## Report Format

For each violation found, report:
- **Severity**: `high` (architectural violation like business logic in admin), `medium` (convention like quotes/imports), `low` (minor style)
- **File and line** where the violation occurs
- **What rule is violated** (reference the rule number)
- **Why it matters** (impact on maintainability, consistency)
- **How to fix** (concrete suggestion)
