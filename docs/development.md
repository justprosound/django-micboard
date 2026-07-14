# Developer guide

This guide covers the supported repository workflow. Architecture decisions live in
`docs/adr/`; domain language and boundaries live in `CONTEXT.md`.

## Requirements

- Python 3.13+
- Django 5.1 through 6.0
- `uv` for dependency and environment management
- Git
- `just` for canonical repository recipes
- PostgreSQL when exercising production behavior; SQLite is sufficient for local tests

## Local setup

```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
uv sync --locked --all-extras
uv run --no-sync pre-commit install --hook-type pre-commit
```

The root `manage.py` loads `example_project.settings` and uses SQLite by default:

```bash
uv run --no-sync python manage.py migrate
uv run --no-sync python manage.py runserver
```

Or run the bootstrap script:

```bash
./start-dev.sh
./start-dev.sh --check-only
```

Docker is optional and no Docker demo tree is required for local development.

## Repository layout

```text
django-micboard/
├── micboard/
│   ├── admin/               # Thin Django admin adapters
│   ├── integrations/        # Manufacturer transports and plugins
│   ├── management/commands/ # Thin management-command adapters
│   ├── models/              # Domain-grouped persistence models
│   ├── services/            # Business logic and orchestration
│   ├── tasks/               # Native Huey wrappers
│   ├── views/               # HTML/HTMX request adapters
│   └── websockets/          # Authenticated Channels routing/consumer
├── example_project/         # Development host project
├── tests/                   # Pytest suite, factories, and settings
├── docs/                    # MkDocs source
├── manage.py                # Root example-project entry point
├── Justfile                 # Canonical development recipes
└── pyproject.toml           # Package and tool configuration
```

## Architecture rules

- Put business logic in a domain service, not in admin, views, tasks, serializers, or commands.
- Pass structured data with Pydantic v2 DTOs and keep public service APIs typed.
- Tasks carry serializable identifiers/DTO data and delegate to services.
- Scope querysets at the boundary; tenant isolation must fail closed.
- Use `select_related`/`prefetch_related` intentionally on hot query paths.
- Use `httpx` for manufacturer transport and close direct clients promptly.
- Use native Huey through `huey.contrib.djhuey`; do not introduce another task queue.
- Update call sites directly when moving APIs; do not add compatibility re-export modules.

Review `.github/copilot-instructions.md` before changing architecture.

## Testing

Run all tests:

```bash
just test
```

Focused examples:

```bash
uv run --no-sync pytest tests/test_lifecycle_hooks.py -v
uv run --no-sync pytest \
  tests/test_lifecycle_hooks.py::TestStatusTransitionValidation::test_valid_transition_discovered_to_online
uv run --no-sync pytest tests/admin/ -v
uv run --no-sync pytest tests/ -k "shure or sennheiser"
```

Coverage gate and inventory:

```bash
just coverage
```

Test layout:

- `tests/admin/`: end-to-end admin smoke flows
- `tests/services/`: domain-service unit/integration coverage
- `tests/test_*security.py`: authorization and authenticated-transport boundaries
- `tests/test_huey_*.py`: native Huey configuration and task wrappers
- `tests/factories/`: reusable model factories

Add a regression test for each bug. For DB code, test rollback/on-commit behavior and tenant scope
where relevant.

## Quality gates

```bash
just lint
just pre-commit
uv run --no-sync bandit -r micboard -ll
uv run --no-sync python manage.py check
```

`just lint` checks Ruff formatting, Ruff rules, and mypy. Pre-commit additionally checks file
syntax, migration drift, and generated migration integrity.

Apply formatting deliberately:

```bash
uv run --no-sync ruff check . --fix
uv run --no-sync ruff format .
```

## Migrations

Never edit or delete existing files in `micboard/migrations/`. When an approved model change
requires schema work, generate the new file through Django:

```bash
uv run --no-sync python manage.py makemigrations micboard micboard_multitenancy
```

Then inspect operations and SQL, and test clean/existing databases. Check drift without writing:

```bash
uv run --no-sync python manage.py makemigrations \
  micboard micboard_multitenancy --check --dry-run
```

Production hosts use `django-safemigrate` according to their deployment process.

## Native Huey

Queued work requires `huey.contrib.djhuey` in `INSTALLED_APPS` and a dictionary at
`settings.HUEY`. Run the consumer with:

```bash
uv run --no-sync python manage.py run_huey
```

Keep network I/O outside long DB transactions. Task functions must delegate business behavior to
services and accept explicit IDs rather than model instances.

## Documentation

Use the [manufacturer plugin development guide](plugin-development.md) when adding or extending a
vendor integration. It documents the live registry, base classes, transport, discovery, streaming,
security, native Huey, and test boundaries.

```bash
just docs
uv run --no-sync mkdocs serve
```

Update `README.md` for user-facing behavior and `CHANGELOG.md` under `[Unreleased]`. Keep commands,
paths, setting names, and optional dependencies aligned with repository code.

## Packaging

Build and validate the distributable artifacts:

```bash
just wheel
```

The validation script installs the built wheel in an isolated uv-managed environment and checks
that reusable-app resources are present.

## Contribution workflow

1. Create a focused branch.
2. Implement the smallest contract-preserving change.
3. Add or update tests and documentation.
4. Run `just lint`, relevant tests, and `just pre-commit`.
5. Use a Conventional Commit message.
6. Open a PR describing behavior, risk, verification, and linked issues.

See `CONTRIBUTING.md` for the complete policy.

## Support

- [GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- [GitHub Discussions](https://github.com/justprosound/django-micboard/discussions)

django-micboard is licensed under AGPL-3.0-or-later.
