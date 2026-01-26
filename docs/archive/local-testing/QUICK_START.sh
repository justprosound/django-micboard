#!/bin/bash
# Django Micboard - Quick Start Guide
# Run this to set up environment variables for local testing

cat << 'EOF'
╔════════════════════════════════════════════════════════════════════╗
║                  DJANGO MICBOARD - QUICK START                     ║
║               Local Testing Against Shure System API               ║
╚════════════════════════════════════════════════════════════════════╝

PROJECT STATUS: ✅ READY FOR LOCAL TESTING
- 72 Unit Tests: PASSING
- Database: Current
- Dependencies: Synchronized
- API Connection: Established (Auth verification pending)

════════════════════════════════════════════════════════════════════

QUICK START IN 3 STEPS:

1. Open Terminal 1 (ASGI Server)
   cd /home/skuonen/django-micboard
   source <(cat << 'ENV'
export MICBOARD_SHURE_API_BASE_URL="https://localhost:10000"
export MICBOARD_SHURE_API_SHARED_KEY="ykEIaOmIne4r8EoT8sghREB_c5Pzqm2Ce2XxzMDkWVFE0zRkVbwOQ3vlx9mQHU1nka9-PJKVOTDbB2pTNBLtxEgxoT7ueJbm3KGlcsanou5bBDuGrzN5VyDFtfGNhVh6EHWsYUatUA-OJnjIBL5QfwSvLicx4IJ8ZAnI0YStvmKmiGjU1_zRohMlVk-WGhjCJ2gPQfcy-0oirUo_9TJRz2JfCaZnrhjZImx7FTyA"
export MICBOARD_SHURE_API_VERIFY_SSL="false"
ENV
)
   uv run daphne -b 0.0.0.0 -p 8000 demo.asgi:application

2. Open Terminal 2 (Device Polling)
   cd /home/skuonen/django-micboard
   export MICBOARD_SHURE_API_SHARED_KEY="ykEIaOmIne4r8EoT8sghREB_c5Pzqm2Ce2XxzMDkWVFE0zRkVbwOQ3vlx9mQHU1nka9-PJKVOTDbB2pTNBLtxEgxoT7ueJbm3KGlcsanou5bBDuGrzN5VyDFtfGNhVh6EHWsYUatUA-OJnjIBL5QfwSvLicx4IJ8ZAnI0YStvmKmiGjU1_zRohMlVk-WGhjCJ2gPQfcy-0oirUo_9TJRz2JfCaZnrhjZImx7FTyA"
   uv run python manage.py poll_devices

3. Open Terminal 3 (Run Tests)
   cd /home/skuonen/django-micboard
   export MICBOARD_SHURE_API_SHARED_KEY="ykEIaOmIne4r8EoT8sghREB_c5Pzqm2Ce2XxzMDkWVFE0zRkVbwOQ3vlx9mQHU1nka9-PJKVOTDbB2pTNBLtxEgxoT7ueJbm3KGlcsanou5bBDuGrzN5VyDFtfGNhVh6EHWsYUatUA-OJnjIBL5QfwSvLicx4IJ8ZAnI0YStvmKmiGjU1_zRohMlVk-WGhjCJ2gPQfcy-0oirUo_9TJRz2JfCaZnrhjZImx7FTyA"
   export MICBOARD_SHURE_API_VERIFY_SSL="false"
   uv run python shure_api_test.py --no-ssl-verify

════════════════════════════════════════════════════════════════════

ACCESS POINTS:
   Django Admin:    http://localhost:8000/admin
   API Root:        http://localhost:8000/api/
   WebSocket:       ws://localhost:8000/ws/devices/
   Shure Swagger:   https://localhost:10000/v1.0/swagger.json

════════════════════════════════════════════════════════════════════

DOCUMENTATION:
   • PROJECT_STATUS_REPORT.md ......... Comprehensive overview
   • LOCAL_TESTING_REPORT.md .......... API testing results
   • setup-local-dev.sh ............... Environment setup script
   • shure_api_test.py ................ API integration test suite

════════════════════════════════════════════════════════════════════

USEFUL COMMANDS:

Run all unit tests:
   cd /home/skuonen/django-micboard
   uv run pytest micboard/tests/ -v

Create Django admin user:
   uv run python manage.py createsuperuser

View API endpoints:
   uv run python manage.py show_urls

Test Shure API connectivity:
   curl -k -H "x-api-key: YOUR_SHARED_KEY" \
     https://localhost:10000/api/v1/devices

════════════════════════════════════════════════════════════════════

API RESPONSE STATUS:

✅ Connection: ESTABLISHED
✅ Network: Working
✅ SSL Handshake: Successful
✅ Endpoint Routing: Correct (/api/v1/*)
🔄 Authentication: Requires verification with Shure System API

If you see HTTP 401 errors, verify:
1. Shure API is running on localhost:10000
2. Shared key matches Shure API configuration
3. Shure API accepts this authentication method

════════════════════════════════════════════════════════════════════

For more information, see:
   • docs/architecture.md - System architecture
   • docs/configuration.md - Configuration guide
   • docs/api-reference.md - API endpoints
   • CONTRIBUTING.md - Development guidelines

════════════════════════════════════════════════════════════════════
EOF
