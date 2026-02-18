# Justfile for django-micboard development
# Modern task automation using just (https://just.systems/)

set dotenv-load

# List available commands
default:
    @just --list

# ============================================================================
# Setup & Installation
# ============================================================================

# Install all dependencies for development
install:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d .venv ]; then uv venv; fi
    uv pip install -e ".[dev,all]"
    uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

# Install minimal dependencies (no dev tools)
install-prod:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d .venv ]; then uv venv; fi
    uv pip install -e ".[all]"

# Upgrade all dependencies to latest versions
upgrade:
    #!/usr/bin/env bash
    set -euo pipefail
    uv pip install --upgrade pip setuptools wheel
    uv pip install --upgrade -e ".[dev,all]"

# ============================================================================
# Code Quality & Linting
# ============================================================================

# Run all linters and formatters
lint:
    @echo "→ Running Ruff format..."
    uv run ruff format .
    @echo "→ Running Ruff check..."
    uv run ruff check --fix .
    @echo "→ Running mypy..."
    uv run mypy micboard
    @echo "→ Running bandit security check..."
    uv run bandit -r micboard -ll
    @echo "✓ All linters passed!"

# Run pre-commit hooks on all files
pre-commit:
    uv run pre-commit run --all-files

# Fix common linting issues automatically
fix:
    uv run ruff format .
    uv run ruff check --fix --unsafe-fixes .

# Type check with mypy
type-check:
    uv run mypy micboard

# Security audit with bandit
security:
    uv run bandit -r micboard -ll -f json -o bandit-report.json
    uv run bandit -r micboard -ll

# ============================================================================
# Testing
# ============================================================================

# Run all tests with coverage
test:
    uv run pytest

# Run tests with verbose output
test-verbose:
    uv run pytest -vv

# Run specific test file or pattern
test-file FILE:
    uv run pytest {{FILE}} -vv

# Run tests matching a keyword expression
test-keyword KEYWORD:
    uv run pytest -k {{KEYWORD}} -vv

# Run only unit tests (fast)
test-unit:
    uv run pytest -m unit

# Run only integration tests
test-integration:
    uv run pytest -m integration

# Run tests without coverage (faster)
test-fast:
    uv run pytest --no-cov

# Run tests and generate HTML coverage report
test-coverage:
    uv run pytest --cov=micboard --cov-report=html --cov-report=term
    @echo "→ Coverage report: htmlcov/index.html"

# Watch tests and re-run on file changes (requires pytest-watch)
test-watch:
    uv run ptw -- -x --testmon

# ============================================================================
# Database Management
# ============================================================================

# Run Django migrations
migrate:
    uv run python manage.py migrate

# Create new migration for app
makemigrations APP="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{APP}}" ]; then
        uv run python manage.py makemigrations
    else
        uv run python manage.py makemigrations {{APP}}
    fi

# Show migration status
showmigrations:
    uv run python manage.py showmigrations

# Reset database (DESTRUCTIVE - asks for confirmation)
reset-db:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "⚠️  This will DELETE all database data!"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        rm -f db.sqlite3
        uv run python manage.py migrate
        echo "✓ Database reset complete"
    else
        echo "Cancelled"
    fi

# ============================================================================
# Development Server
# ============================================================================

# Run Django development server
run PORT="8000":
    uv run python manage.py runserver {{PORT}}

# Run development server with example project
run-example:
    cd example_project && uv run python manage.py migrate
    cd example_project && uv run python manage.py runserver

# Create Django superuser
createsuperuser:
    uv run python manage.py createsuperuser

# Django shell
shell:
    uv run python manage.py shell

# Django shell with shell_plus (if django-extensions installed)
shell-plus:
    uv run python manage.py shell_plus

# ============================================================================
# Management Commands
# ============================================================================

# Run device discovery
discover MANUFACTURER="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{MANUFACTURER}}" ]; then
        uv run python manage.py device_discovery
    else
        uv run python manage.py device_discovery --manufacturer={{MANUFACTURER}}
    fi

# Poll devices for status updates
poll MANUFACTURER="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{MANUFACTURER}}" ]; then
        uv run python manage.py poll_devices
    else
        uv run python manage.py poll_devices --manufacturer={{MANUFACTURER}}
    fi

# Check Shure API health
check-shure-api:
    uv run python manage.py shure_api_health_check

# Initialize settings system
init-settings:
    uv run python manage.py init_settings

# Archive audit logs
archive-logs:
    uv run python manage.py archive_audit_logs

# ============================================================================
# Documentation
# ============================================================================

# Build documentation
docs:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d .venv ]; then uv venv; fi
    uv pip install -e ".[docs]"
    uv run mkdocs build

# Serve documentation locally
serve-docs:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d .venv ]; then uv venv; fi
    uv pip install -e ".[docs]"
    uv run mkdocs serve

# ============================================================================
# Build & Release
# ============================================================================

# Build distribution packages
build:
    uv run python -m build

# Clean build artifacts and cache
clean:
    rm -rf build/ dist/ *.egg-info htmlcov/ .coverage .pytest_cache/ .ruff_cache/ .mypy_cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    @echo "✓ Cleaned build artifacts"

# Clean and rebuild
rebuild: clean build

# ============================================================================
# Utilities
# ============================================================================

# Check for outdated dependencies
outdated:
    uv pip list --outdated

# Show dependency tree
deps-tree:
    uv pip install pipdeptree
    uv run pipdeptree

# Generate requirements.txt from pyproject.toml
requirements:
    uv pip compile pyproject.toml -o requirements.txt

# Run Django checks
check:
    uv run python manage.py check

# Validate project structure
validate:
    @echo "→ Running Django checks..."
    uv run python manage.py check
    @echo "→ Running linters..."
    just lint
    @echo "→ Running tests..."
    just test
    @echo "✓ All validations passed!"

# ============================================================================
# CI/CD Helpers
# ============================================================================

# Run full CI pipeline locally
ci:
    @echo "→ Installing dependencies..."
    just install
    @echo "→ Running linters..."
    just lint
    @echo "→ Running security checks..."
    just security
    @echo "→ Running tests with coverage..."
    just test
    @echo "✓ CI pipeline complete!"

# Quick pre-commit validation (runs before commits)
quick-check:
    @echo "→ Running quick checks..."
    uv run ruff format --check .
    uv run ruff check .
    uv run pytest -x --no-cov
    @echo "✓ Quick checks passed!"
