#!/bin/bash
# Live Integration Test Suite for django-micboard with Shure System API
# Tests all workflows end-to-end with real API data

set -e

echo "======================================================================="
echo "django-micboard Live Integration Test Suite"
echo "======================================================================="
echo ""

# Load environment
if [ -f .env.local ]; then
    export $(cat .env.local | xargs)
    echo "✓ Loaded environment from .env.local"
else
    echo "✗ .env.local not found"
    exit 1
fi

# 1. API Health Check
echo ""
echo "1. Shure System API Health Check"
echo "-----------------------------------------------------------------------"
python scripts/shure_api_health_check.py

# 2. Database Setup
echo ""
echo "2. Database Setup"
echo "-----------------------------------------------------------------------"
python manage.py migrate --noinput
echo "✓ Migrations applied"

# 3. Create superuser if needed (non-interactive)
echo ""
echo "3. Admin User Setup"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('✓ Created admin user (admin/admin123)')
else:
    print('✓ Admin user already exists')
"

# 4. Initialize manufacturer registry
echo ""
echo "4. Manufacturer Registry Initialization"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from micboard.models import Manufacturer
from micboard.services.manufacturer_service import ServiceRegistry

# Ensure Shure manufacturer exists
shure, created = Manufacturer.objects.get_or_create(
    code='shure',
    defaults={
        'name': 'Shure',
        'is_active': True
    }
)
if created:
    print('✓ Created Shure manufacturer record')
else:
    print('✓ Shure manufacturer exists')

# Initialize service registry
registry = ServiceRegistry()
print(f'✓ Service registry initialized with {len(registry._services)} services')
"

# 5. Test device discovery
echo ""
echo "5. Device Discovery Test"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.services.manufacturer_service import ServiceRegistry

client = ShureSystemAPIClient(
    base_url='https://localhost:10000',
    verify_ssl=False
)

devices = client.devices.get_devices()
print(f'✓ Retrieved {len(devices)} devices from API')

# Show device types
from collections import Counter
types = Counter(d.get('type', 'UNKNOWN') for d in devices)
for device_type, count in types.items():
    print(f'  {device_type}: {count}')
"

# 6. Test logging mode service
echo ""
echo "6. Logging Mode Service Test"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from micboard.services.logging_mode import LoggingModeService

# Test mode switching
LoggingModeService.set_mode('high', duration_minutes=5)
mode = LoggingModeService.get_current_mode()
print(f'✓ Set logging mode to: {mode}')

# Test verbosity checks
verbose = LoggingModeService.should_log_verbose()
print(f'✓ Verbose logging enabled: {verbose}')
"

# 7. Test kiosk service
echo ""
echo "7. Kiosk Service Test"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from micboard.services.kiosk import KioskService
from micboard.models import DisplayWall

# Try to get kiosk data (may fail if no display walls configured)
try:
    data = KioskService.get_display_wall_data(wall_id=1)
    print(f'✓ Kiosk service functional')
except Exception as e:
    print(f'⚠ Kiosk data unavailable (expected if no display walls): {e}')
"

# 8. Test audit service
echo ""
echo "8. Audit Service Test"
echo "-----------------------------------------------------------------------"
python manage.py shell -c "
from micboard.services.audit import AuditService

# Test retention configuration
retention = AuditService.get_retention_days('activity')
print(f'✓ Audit retention: {retention} days')

# Test archive path
archive_path = AuditService.get_archive_path()
print(f'✓ Archive path: {archive_path}')
"

# 9. Test management commands
echo ""
echo "9. Management Commands Test"
echo "-----------------------------------------------------------------------"
python manage.py set_logging_mode normal
echo "✓ set_logging_mode command works"

# 10. Start dev server (background)
echo ""
echo "10. Development Server Test"
echo "-----------------------------------------------------------------------"
echo "Starting development server on port 8000..."
python manage.py runserver 0.0.0.0:8000 > /dev/null 2>&1 &
SERVER_PID=$!
echo "✓ Server started (PID: $SERVER_PID)"
sleep 3

# Test HTTP endpoints
echo "Testing HTTP endpoints..."
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ > /tmp/http_test
HTTP_CODE=$(cat /tmp/http_test)
if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "302" ]; then
    echo "✓ Index page accessible (HTTP $HTTP_CODE)"
else
    echo "✗ Index page failed (HTTP $HTTP_CODE)"
fi

# Stop server
kill $SERVER_PID 2>/dev/null || true
echo "✓ Server stopped"

# Summary
echo ""
echo "======================================================================="
echo "Integration Test Complete"
echo "======================================================================="
echo ""
echo "Next Steps:"
echo "  1. Start dev server: python manage.py runserver"
echo "  2. Visit: http://localhost:8000"
echo "  3. Login: admin / admin123"
echo "  4. Test HTMX partial endpoints:"
echo "     - /alerts/ (5s polling)"
echo "     - /assignments/ (5s polling)"
echo "     - /chargers/ (kiosk view)"
echo ""
echo "Available scripts:"
echo "  python scripts/shure_api_health_check.py --full"
echo "  python manage.py set_logging_mode high --duration 60"
echo "  python manage.py archive_audit_logs --retention-days 30"
echo ""
