#!/usr/bin/env bash
# Run the local release-readiness gates without publishing artifacts.

set -euo pipefail

just uv-check

uv sync --locked --all-extras
uv run --no-sync prek run --all-files --show-diff-on-failure
uv run --no-sync pytest
uv run --no-sync python -m django check --settings=tests.settings
uv run --no-sync python -m django makemigrations micboard micboard_multitenancy \
    --check --dry-run --settings=tests.settings
uv build --sdist --clear
uv build --wheel dist/django_micboard-*.tar.gz
uv run --no-project python scripts/validate_wheel.py dist/django_micboard-*.whl
uv run --no-project --with dist/django_micboard-*.whl \
    python scripts/smoke_test_installed_wheel.py

echo "Release-readiness checks passed. Start .github/workflows/prepare-release.yml from main."
