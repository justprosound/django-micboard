# Project command recipes

set shell := ["bash", "-c"]

default:
    @echo "Available commands:"
    @echo "  install    - Install dependencies and prek hooks"
    @echo "  lint       - Run all linting and type checks"
    @echo "  test       - Run tests"
    @echo "  coverage   - Run tests with the CI coverage threshold"
    @echo "  migrate    - Run migrations"
    @echo "  docs       - Build the documentation site"
    @echo "  serve-docs - Serve the documentation site locally on port 9000"
    @echo "  docs-api   - Regenerate the Python API reference from docstrings"
    @echo "  docs-verify - Validate documentation frontmatter, coverage, and links"
    @echo "  docs-e2e   - Run the documentation search, brand, and accessibility suite"
    @echo "  example    - Run example project"
    @echo "  wheel      - Build, validate, and smoke-test the reusable-app wheel"
    @echo "  type-check - Run type checks specifically"
    @echo "  prs        - List open PRs and their current CI check status"
    @echo "  deps-upgrade - Upgrade dependencies, regenerate locks, and run checks"

# Fail early before any environment or command operation.
uv-check:
    @command -v uv >/dev/null 2>&1 || { echo "error: uv is required" >&2; exit 1; }
    @uv --version >/dev/null

# The documentation site is an Astro Starlight build, so it needs Node and npm.
npm-check:
    @command -v npm >/dev/null 2>&1 || { echo "error: npm is required for the docs site" >&2; exit 1; }
    @npm --version >/dev/null

# Documentation recipes need the locked Node dependency tree in place. Reinstall when the
# lockfile is newer than the tree, so a lockfile update or branch switch cannot leave
# stale packages behind.
docs-deps: npm-check
    @{ [ -d node_modules ] && [ node_modules -nt package-lock.json ]; } || npm ci

# Install dependencies and prek hooks
install: uv-check npm-check
    uv sync --locked --all-extras
    npm ci
    uv run --no-sync prek install -f --prepare-hooks --hook-type pre-commit

# Run all linting and type checks
lint: uv-check
    uv run --no-sync ruff format --check micboard tests scripts
    uv run --no-sync ruff check micboard tests scripts
    uv run --no-sync python -m mypy micboard

# Run every configured hook against the repository with prek.
prek: uv-check
    uv run --no-sync prek run --all-files --show-diff-on-failure

# Run tests
test: uv-check
    uv run --no-sync pytest

# Run the full branch-coverage suite with the non-regression floor used in CI.
coverage: uv-check
    uv run --no-sync pytest tests/ \
        --cov=micboard \
        --cov-report=html:htmlcov \
        --cov-report=xml \
        --cov-report=term-missing:skip-covered \
        --cov-fail-under=95
    uv run --no-sync python scripts/check_coverage_inventory.py

# Run migrations
migrate: uv-check
    uv run --no-sync python manage.py migrate

# Build the documentation site into site/
docs: docs-deps
    npm run docs:build

# Serve the documentation site locally with hot reload
serve-docs: docs-deps
    npm run docs:dev

# Regenerate the committed Python API reference from source docstrings
docs-api: uv-check
    uv run --no-sync python scripts/generate_api_docs.py

# Validate documentation frontmatter, reference freshness, page coverage, and links
# against a freshly built site rather than whatever is left in site/.
docs-verify: uv-check docs
    uv run --no-sync python scripts/check_docs_frontmatter.py
    uv run --no-sync python scripts/generate_api_docs.py --check
    uv run --no-sync python scripts/check_docs_coverage.py
    uv run --no-sync python scripts/check_docs_links.py

# Repair missing documentation frontmatter in place
docs-frontmatter: uv-check
    uv run --no-sync python scripts/check_docs_frontmatter.py --fix

# Run the documentation search, brand, and accessibility suite against the built site
docs-e2e: docs-deps
    npm run docs:build
    npx playwright install chromium
    npm run docs:e2e

# Run example project
example: uv-check
    uv run --no-sync python manage.py runserver

# Build the distributable artifact, verify its contents, and import it outside the source tree.
wheel: uv-check
    uv build --no-sources --sdist --clear
    uv build --no-sources --wheel dist/django_micboard-*.tar.gz
    uv run --no-project python scripts/validate_wheel.py dist/django_micboard-*.whl
    uv run --no-project --with dist/django_micboard-*.whl \
        python scripts/smoke_test_installed_wheel.py

# Run type checks specifically
type-check: uv-check
    uv run --no-sync python -m mypy micboard

# List open PRs and their current CI check status
prs:
    @gh pr list

# Upgrade lockfiles and run quality checks
deps-upgrade: uv-check npm-check
    uv lock --upgrade
    uv sync --locked --all-extras
    npm update
    just lint
    just test
