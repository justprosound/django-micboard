# Agent Instructions

## Package Managers
- Use **`uv`** exclusively for Python environments and packages: `uv sync --locked --all-extras` (never use `pip`, `pipx`, `poetry`, or `venv`).
- Use **`npm`** for the Astro Starlight documentation toolchain: `npm ci`.
- Use **`just install`** to install both dependency trees and configure `prek` hooks.

## Commands
| Task | Command |
|------|---------|
| Test file | `uv run --no-sync pytest tests/test_settings_service.py -v` |
| Test marker | `uv run --no-sync pytest -m "unit or integration or django_db"` |
| Test suite & coverage | `just coverage` |
| Lint file | `uv run --no-sync ruff check path/to/file.py` |
| Format file | `uv run --no-sync ruff format path/to/file.py` |
| Typecheck file | `uv run --no-sync python -m mypy path/to/file.py` |
| Security scan | `uv run --no-sync bandit -r micboard -ll` |
| Git hooks | `uv run --no-sync prek run --all-files` |
| Regenerate API docs | `just docs-api` |
| Verify docs | `just docs-verify` |
| Validate changelog | `just changelog-check` |

## External References
| Need | File |
|------|------|
| Setup & PR workflow | `CONTRIBUTING.md` |
| Canonical architecture & coding rules | `.github/copilot-instructions.md` |
| System & domain architecture | `docs/architecture.md` |
| Documentation platform (Starlight) | `docs/adr/013-documentation-platform-starlight.md` |
| Security policy | `SECURITY.md` |
| Domain glossary & ADRs | `docs/agents/domain.md` |
| GitHub issue tracker conventions | `docs/agents/issue-tracker.md` |
| Issue triage labels | `docs/agents/triage-labels.md` |

## Key Conventions
- Organize code by domain under `micboard/{services,tasks,serializers,admin,api}/<domain>/` and keep files under ~400 lines.
- Isolate business logic in the Service Layer (`DefaultsService`, `UpsertService`, `BulkPersistService`); keep views, admin, tasks, and serializers as thin wrappers.
- Pass data across layers with Pydantic v2 DTOs inheriting from `PydanticBaseDTO` and mapped via `DTOMapper`.
- Annotate all public functions, methods, services, and DTOs with type hints.
- Use native Huey (`huey.contrib.djhuey`) for background tasks and `httpx` for HTTP requests (`Celery`, `django-q2`, and `requests` are deprecated).
- Log exceptions in `except Exception:` blocks using `logger.exception("Message %s", arg)` with lazy `%s` formatting.
- Update all call sites directly when moving or removing APIs; never leave compatibility shims or re-export aliases.
- Generate new migrations only for approved schema changes and run them with `django-safemigrate`; never edit or delete existing files in `micboard/migrations/`.
- Regenerate `docs/api/reference/` with `just docs-api` (`scripts/generate_api_docs.py`); do not edit generated reference files by hand or import Django during docs builds.
- Add one `changelog.d/pr-<number>.md` fragment per pull request.
- Format commit messages with Conventional Commits (`feat:`, `fix:`, etc.) and never include `Co-Authored-By` trailers.
