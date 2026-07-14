#!/usr/bin/env bash

# Prepare django-micboard for local development, then start the example project.
# Dependencies and commands always run through uv. Docker is optional and is not
# required by the repository's SQLite-backed example project.

set -euo pipefail

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() {
    echo -e "${BLUE}info${NC} $*"
}

log_success() {
    echo -e "${GREEN}ok${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}warning${NC} $*"
}

log_error() {
    echo -e "${RED}error${NC} $*" >&2
}

check_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_error "Required command '$1' was not found."
        exit 1
    fi
}

if [ "${1:-}" = "--help" ]; then
    echo "Usage: ./start-dev.sh [--check-only]"
    exit 0
fi

if [ "${1:-}" != "" ] && [ "${1:-}" != "--check-only" ]; then
    log_error "Unknown option: $1"
    exit 2
fi

check_command uv
check_command git

if [ ! -f pyproject.toml ] || [ ! -f manage.py ]; then
    log_error "Run this script from the django-micboard repository root."
    exit 1
fi

log_info "Syncing the locked environment with all supported extras..."
uv sync --locked --all-extras
log_success "Dependencies synchronized"

log_info "Installing the repository pre-commit hook..."
uv run --no-sync pre-commit install --hook-type pre-commit
log_success "Pre-commit hook installed"

log_info "Running Django system checks..."
uv run --no-sync python manage.py check
log_success "Django system checks passed"

log_info "Checking for model changes without generating migration files..."
uv run --no-sync python manage.py makemigrations \
    micboard micboard_multitenancy --check --dry-run
log_success "Migration state matches the models"

log_info "Applying checked-in migrations to the local development database..."
uv run --no-sync python manage.py migrate
log_success "Checked-in migrations applied"

if command -v docker >/dev/null 2>&1; then
    log_info "Docker is available for host-project experiments; local setup does not require it."
else
    log_warning "Docker not found; continuing with the SQLite-backed example project."
fi

if [ "${1:-}" = "--check-only" ]; then
    log_success "Development environment is ready"
    exit 0
fi

log_info "Starting the example project at http://127.0.0.1:8000/"
log_info "Set MICBOARD_SHURE_API_BASE_URL and MICBOARD_SHURE_API_SHARED_KEY as needed."
uv run --no-sync python manage.py runserver
