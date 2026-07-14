#!/usr/bin/env bash
# Run the local release-readiness gates without publishing artifacts.

set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is required" >&2
    exit 1
fi

uv sync --locked --all-extras
uv run --no-sync pre-commit run --all-files --show-diff-on-failure
uv run --no-sync pytest
uv run --no-sync python -m django check --settings=tests.settings
uv run --no-sync python -m django makemigrations micboard micboard_multitenancy \
    --check --dry-run --settings=tests.settings
uv build --sdist --clear
uv build --wheel dist/django_micboard-*.tar.gz
uv run --no-project python scripts/validate_wheel.py dist/django_micboard-*.whl
uv run --no-project --with dist/django_micboard-*.whl \
    python scripts/smoke_test_installed_wheel.py

echo "Release-readiness checks passed. Publish only through .github/workflows/release.yml."
