#!/bin/bash

# Django Micboard Development Setup Script
#
# This script sets up the complete development environment including:
# - Python virtual environment with all dev dependencies
# - Pre-commit hooks for code quality enforcement
# - Django migrations and system checks
# - Docker demo environment with Shure API support
#
# SECURITY NOTE:
# - This script reads the Shure shared key from environment or Windows installation
# - NEVER hardcode credentials in this script or pass them as arguments
# - Use .env.local for local configuration (this file is in .gitignore)
# - For detailed setup instructions, see: docs/CONFIGURATION.md

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $*"
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command '$1' not found. Please install it and try again."
        exit 1
    fi
}

# Validate prerequisites
log_info "Checking prerequisites..."
check_command python3
check_command uv
check_command docker
check_command git

# Verify we're in the project root
if [ ! -f pyproject.toml ]; then
    log_error "pyproject.toml not found. Please run this script from the project root."
    exit 1
fi

log_success "All prerequisites found"
echo ""

# Sync dependencies with uv (recreates venv if needed)
log_info "Syncing dependencies with uv (this may take a minute)..."
if uv sync --frozen --extra dev 2>&1 | tail -5; then
    log_success "Dependencies synchronized"
else
    log_error "Failed to sync dependencies"
    exit 1
fi
echo ""

# Setup pre-commit hooks
log_info "Setting up pre-commit hooks..."
if uv run pre-commit install --install-hooks 2>&1 | tail -3; then
    log_success "Pre-commit hooks installed"
else
    log_warning "Failed to set up pre-commit hooks (non-fatal)"
fi
echo ""

# Validate Django system configuration
log_info "Validating Django system configuration..."
unset DJANGO_SETTINGS_MODULE
if uv run manage.py check 2>&1 | tail -5; then
    log_success "Django system checks passed"
else
    log_error "Django system checks failed"
    exit 1
fi
echo ""

# Run migrations
log_info "Running database migrations..."
if uv run manage.py makemigrations micboard 2>&1 | tail -3; then
    log_success "Migrations created"
fi
if uv run manage.py migrate 2>&1 | tail -3; then
    log_success "Migrations applied"
else
    log_error "Database migration failed"
    exit 1
fi
echo ""

# Check for linting tools availability
log_info "Checking code quality tools..."
HAVE_RUFF=false
HAVE_MYPY=false

if uv run ruff --version &> /dev/null; then
    log_success "ruff is available (linting)"
    HAVE_RUFF=true
fi

if uv run mypy --version &> /dev/null; then
    log_success "mypy is available (type checking)"
    HAVE_MYPY=true
fi

if [ "$HAVE_RUFF" = true ] || [ "$HAVE_MYPY" = true ]; then
    log_info "Run 'uv run ruff check micboard/' to lint code"
    log_info "Run 'uv run mypy micboard/' to check types"
fi
echo ""


# Detect Shure shared key
log_info "Detecting Shure API credentials..."
SHARED_KEY="${MICBOARD_SHURE_API_SHARED_KEY:-}"

if [ -z "$SHARED_KEY" ]; then
    # Try to read from WSL2 Windows installation
    if [ -f /proc/version ] && grep -q -i "wsl2\|microsoft" /proc/version; then
        log_info "WSL2 detected. Checking for Shure System API..."
        SHARED_KEY_FILE="/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt"
        if [ -f "$SHARED_KEY_FILE" ]; then
            SHARED_KEY=$(cat "$SHARED_KEY_FILE" | tr -d '\r\n')
            if [ -n "$SHARED_KEY" ]; then
                log_success "Found Shure shared key from Windows installation"
            else
                log_warning "Shure key file exists but is empty"
            fi
        else
            log_warning "Shure shared key file not found at: $SHARED_KEY_FILE"
            log_info "Make sure Shure System API is installed on Windows"
        fi
    fi
fi

if [ -n "$SHARED_KEY" ]; then
    log_success "Shure API credentials available"
else
    log_warning "Shure API credentials not configured"
    log_info "You can set credentials with:"
    log_info "  export MICBOARD_SHURE_API_SHARED_KEY='your-key-here'"
    log_info "  $0"
fi
echo ""

# Prepare Docker demo environment (optional)
log_info "Checking for Docker demo environment..."

if [ -d "demo/docker" ]; then
    log_info "Found demo/docker directory"

    log_info "Building Docker image..."
    if docker compose -f demo/docker/docker-compose.yml build 2>&1 | tail -5; then
        log_success "Docker image built"
    else
        log_error "Docker build failed"
        exit 1
    fi

    echo ""
    log_success "Development environment is ready!"
    echo ""
    log_info "Starting demo container..."
    echo ""
    log_info "Demo will be available at: ${BLUE}http://localhost:8000${NC}"
    log_info "Admin interface: ${BLUE}http://localhost:8000/admin/${NC}"
    log_info ""

    if [ -n "$SHARED_KEY" ]; then
        log_success "Starting with Shure API credentials"
        echo ""
        cd demo/docker || exit 1
        MICBOARD_SHURE_API_SHARED_KEY="$SHARED_KEY" docker compose up
    else
        log_warning "Starting WITHOUT Shure API credentials"
        echo ""
        log_info "To connect to a Shure System API:"
        log_info ""
        log_info "  1. Set the shared key:"
        log_info "     export MICBOARD_SHURE_API_SHARED_KEY='your-key-here'"
        log_info ""
        log_info "  2. Restart this script:"
        log_info "     ./start-dev.sh"
        log_info ""
        log_info "  Or run directly with Docker:"
        log_info "     MICBOARD_SHURE_API_SHARED_KEY=your-key docker compose up"
        log_info ""
        log_info "To find your Shure shared key:"
        log_info "  Windows: C:\\ProgramData\\Shure\\SystemAPI\\Standalone\\Security\\sharedkey.txt"
        log_info "  Linux/Mac: Check your Shure System API installation"
        log_info ""
        cd demo/docker || exit 1
        docker compose up
    fi
else
    # Run Django dev server directly
    log_warning "demo/docker directory not found; running Django dev server directly"
    echo ""
    log_success "Development environment is ready!"
    echo ""
    log_info "Starting Django development server..."
    echo ""
    log_info "Demo will be available at: ${BLUE}http://localhost:8000${NC}"
    log_info "Admin interface: ${BLUE}http://localhost:8000/admin/${NC}"
    log_info ""

    uv run manage.py runserver
fi
