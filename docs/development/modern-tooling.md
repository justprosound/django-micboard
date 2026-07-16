# Development Tooling

django-micboard uses one reproducible toolchain: `uv` for dependency/environment management, `just` for repository recipes, and local pre-commit hooks that execute inside the uv-managed environment.

## Bootstrap

From the repository root:

```bash
uv sync --locked --all-extras
uv run --no-sync pre-commit install --hook-type pre-commit
```

The equivalent recipe is:

```bash
just install
```

Every Justfile recipe depends on `uv-check`, which fails before running when `uv` is unavailable. Do not create environments or install project dependencies with other Python package managers.

## Justfile Recipes

Run `just` to display the canonical list.

| Recipe | Purpose |
| --- | --- |
| `just install` | Sync the locked environment with all extras and install the pre-commit hook |
| `just lint` | Check Ruff formatting, Ruff rules, and mypy |
| `just pre-commit` | Run every configured hook against the repository |
| `just test` | Run the pytest suite |
| `just coverage` | Run tests with the CI floor and validate the coverage inventory |
| `just migrate` | Apply checked-in migrations to the example database |
| `just docs` | Build the MkDocs documentation site |
| `just example` | Start the root `manage.py` example project |
| `just wheel` | Build source/wheel artifacts and validate the installed package contents |
| `just type-check` | Run mypy for `micboard` |

Examples:

```bash
just lint
just test
just coverage
just example
```

`manage.py` lives at repository root and points to `example_project.settings`; do not change into `example_project/` before invoking it.

## Local Setup Script

`start-dev.sh` provides an end-to-end local bootstrap:

```bash
./start-dev.sh
```

It syncs the locked environment, installs the hook, runs Django checks, verifies migration drift without writing migration files, applies checked-in migrations, and starts the example server. Docker is optional. Use check-only mode when a server should not remain running:

```bash
./start-dev.sh --check-only
```

## Pre-commit Hooks

The checked-in configuration is the source of truth. Current hooks cover:

- trailing whitespace and final newlines
- YAML, JSON, and TOML syntax
- merge-conflict markers and Python debug statements
- Ruff lint/format checks
- mypy
- Django migration drift
- generated migration integrity

Run all hooks:

```bash
just pre-commit
```

Run one hook:

```bash
uv run --no-sync pre-commit run ruff-check --all-files
```

The repository does not configure a commit-message hook. Commit messages still follow the Conventional Commits format documented in `CONTRIBUTING.md`.

## Direct Commands

Recipes are preferred, but direct commands remain useful for focused work:

```bash
uv run --no-sync pytest tests/test_lifecycle_hooks.py -vv
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync python -m mypy micboard
uv run --no-sync bandit -r micboard -ll
uv run --no-sync mkdocs build
```

After `uv sync`, use `--no-sync` for repeatable commands that must not alter the environment.

## Migration Policy

Never edit existing files under `micboard/migrations/`. Schema changes must be represented by a migration generated through Django's `makemigrations` command and reviewed before commit.

Check for drift without creating files:

```bash
uv run --no-sync python manage.py makemigrations \
  micboard micboard_multitenancy --check --dry-run
```

Apply checked-in migrations:

```bash
uv run --no-sync python manage.py migrate
```

## Dependency Changes

Edit `pyproject.toml` through uv commands and commit the resulting `uv.lock` update:

```bash
uv add package-name
uv add --dev package-name
uv lock --upgrade-package package-name
```

Then run:

```bash
just lint
just test
just pre-commit
```

## Troubleshooting

### `uv` is missing

Install `uv` through an approved platform package or the official installer, then confirm:

```bash
uv --version
```

### Environment is stale

```bash
uv sync --locked --all-extras
```

### One pre-commit hook fails

Run that exact hook with verbose output, fix the reported file, then run all hooks:

```bash
uv run --no-sync pre-commit run HOOK_ID --all-files --verbose
just pre-commit
```

### Migration drift fails

Do not hand-edit a migration to silence the check. Confirm whether a model change is intentional, then generate a new migration with Django and review its operations and SQL.

## References

- [uv documentation](https://docs.astral.sh/uv/)
- [just manual](https://just.systems/man/en/)
- [pre-commit documentation](https://pre-commit.com/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [pytest documentation](https://docs.pytest.org/)