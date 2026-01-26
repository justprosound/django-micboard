#!/bin/bash
# Django Micboard - Local Development Environment Setup
# This script configures the environment and starts the development services

set -e

PROJECT_ROOT="/home/skuonen/django-micboard"
cd "$PROJECT_ROOT"

# Configure Shure API credentials
export MICBOARD_SHURE_API_BASE_URL="https://localhost:10000"
export MICBOARD_SHURE_API_SHARED_KEY="ykEIaOmIne4r8EoT8sghREB_c5Pzqm2Ce2XxzMDkWVFE0zRkVbwOQ3vlx9mQHU1nka9-PJKVOTDbB2pTNBLtxEgxoT7ueJbm3KGlcsanou5bBDuGrzN5VyDFtfGNhVh6EHWsYUatUA-OJnjIBL5QfwSvLicx4IJ8ZAnI0YStvmKmiGjU1_zRohMlVk-WGhjCJ2gPQfcy-0oirUo_9TJRz2JfCaZnrhjZImx7FTyA"
export MICBOARD_SHURE_API_VERIFY_SSL="false"  # For self-signed certificates

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   Django Micboard - Local Development Environment             ║"
echo "║   Testing against Shure System API on https://localhost:10000 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "Environment Configuration:"
echo "  MICBOARD_SHURE_API_BASE_URL: $MICBOARD_SHURE_API_BASE_URL"
echo "  MICBOARD_SHURE_API_SHARED_KEY: ${MICBOARD_SHURE_API_SHARED_KEY:0:20}...${MICBOARD_SHURE_API_SHARED_KEY: -20}"
echo "  MICBOARD_SHURE_API_VERIFY_SSL: $MICBOARD_SHURE_API_VERIFY_SSL"
echo ""

# Verify dependencies are synced
echo "Verifying dependencies..."
uv sync --frozen --extra dev > /dev/null 2>&1
echo "✓ Dependencies ready"
echo ""

# Verify database migrations
echo "Checking database..."
uv run python manage.py migrate > /dev/null 2>&1
echo "✓ Database up to date"
echo ""

echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Services to start in separate terminals:"
echo ""
echo "Terminal 1 (ASGI Server with WebSocket support):"
echo "  cd $PROJECT_ROOT"
echo "  export MICBOARD_SHURE_API_BASE_URL=$MICBOARD_SHURE_API_BASE_URL"
echo "  export MICBOARD_SHURE_API_SHARED_KEY=$MICBOARD_SHURE_API_SHARED_KEY"
echo "  export MICBOARD_SHURE_API_VERIFY_SSL=$MICBOARD_SHURE_API_VERIFY_SSL"
echo "  uv run daphne -b 0.0.0.0 -p 8000 demo.asgi:application"
echo ""
echo "Terminal 2 (Device Polling Task):"
echo "  cd $PROJECT_ROOT"
echo "  export MICBOARD_SHURE_API_SHARED_KEY=$MICBOARD_SHURE_API_SHARED_KEY"
echo "  uv run python manage.py poll_devices"
echo ""
echo "Terminal 3 (Run API Tests):"
echo "  cd $PROJECT_ROOT"
echo "  export MICBOARD_SHURE_API_SHARED_KEY=$MICBOARD_SHURE_API_SHARED_KEY"
echo "  export MICBOARD_SHURE_API_VERIFY_SSL=$MICBOARD_SHURE_API_VERIFY_SSL"
echo "  uv run python shure_api_test.py --no-ssl-verify"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Access points:"
echo "  Django Admin:    http://localhost:8000/admin"
echo "  API Root:        http://localhost:8000/api/"
echo "  WebSocket:       ws://localhost:8000/ws/devices/"
echo "  Shure Swagger:   https://localhost:10000/v1.0/swagger.json"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
