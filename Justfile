# Project command recipes

set shell := ["bash", "-c"]

default:
    @echo "Available commands:"
    @echo "  install    - Install dependencies and pre-commit hooks"
    @echo "  lint       - Run all linting and type checks"
    @echo "  test       - Run tests"
    @echo "  coverage   - Run tests with the CI coverage threshold"
    @echo "  migrate    - Run migrations"
    @echo "  docs       - Build documentation"
    @echo "  example    - Run example project"
    @echo "  wheel      - Build and validate the reusable-app wheel"
    @echo "  type-check - Run type checks specifically"

# Fail early before any environment or command operation.
uv-check:
    @command -v uv >/dev/null 2>&1 || { echo "error: uv is required" >&2; exit 1; }
    @uv --version >/dev/null

# Install dependencies and pre-commit hooks
install: uv-check
    uv sync --locked --all-extras
    uv run --no-sync pre-commit install --hook-type pre-commit

# Run all linting and type checks
lint: uv-check
    uv run --no-sync ruff format --check .
    uv run --no-sync ruff check .
    uv run --no-sync python -m mypy micboard

# Run every configured pre-commit hook against the repository.
pre-commit: uv-check
    uv run --no-sync pre-commit run --all-files --show-diff-on-failure

# Run tests
test: uv-check
    uv run --no-sync pytest

# Run the full suite with the current non-regression floor used in CI.
# Ratchet this toward the 60% target as the remaining test phases land.
coverage: uv-check
    uv run --no-sync pytest tests/ \
        --cov=micboard \
        --cov-report=html:htmlcov \
        --cov-report=xml \
        --cov-report=term-missing:skip-covered \
        --cov-fail-under=49
    uv run --no-sync python scripts/check_coverage_inventory.py

# Run migrations
migrate: uv-check
    uv run --no-sync python manage.py migrate

# Build documentation
docs: uv-check
    uv run --no-sync mkdocs build

# Run example project
example: uv-check
    uv run --no-sync python manage.py runserver

# Build the distributable artifact and verify it contains the complete app.
wheel: uv-check
    uv build --sdist --clear
    uv build --wheel dist/django_micboard-*.tar.gz
    uv run --no-project python scripts/validate_wheel.py dist/django_micboard-*.whl

# Run type checks specifically
type-check: uv-check
    uv run --no-sync python -m mypy micboard
