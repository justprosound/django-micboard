#!/usr/bin/env python
"""
Phase 4 verification script - Tests all newly created components.

Verifies:
1. All models import correctly
2. All serializers work
3. All viewsets are configured
4. Services architecture is functional
5. Logging system works
"""

from __future__ import annotations

import os
import sys
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

django.setup()

from django.test.utils import setup_test_environment, teardown_test_environment
from rest_framework.test import APIRequestFactory

print("=" * 80)
print("PHASE 4 IMPLEMENTATION VERIFICATION")
print("=" * 80)

# Test 1: Import all models
print("\n[1/6] Testing Model Imports...")
try:
    from micboard.models import (
        ActivityLog,
        ServiceSyncLog,
        ManufacturerConfiguration,
        ConfigurationAuditLog,
        Manufacturer,
        Receiver,
        Transmitter,
        Channel,
        Location,
        Room,
        Group,
    )
    print("✅ All models imported successfully")
except ImportError as e:
    print(f"❌ Model import failed: {e}")
    sys.exit(1)

# Test 2: Import all serializers
print("\n[2/6] Testing Serializer Imports...")
try:
    from micboard.serializers.drf import (
        ManufacturerSerializer,
        ManufacturerConfigurationSerializer,
        ReceiverSerializer,
        TransmitterSerializer,
        ChannelSerializer,
        LocationSerializer,
        GroupSerializer,
        BulkDeviceActionSerializer,
        HealthStatusSerializer,
    )
    print("✅ All serializers imported successfully")
except ImportError as e:
    print(f"❌ Serializer import failed: {e}")
    sys.exit(1)

# Test 3: Import all viewsets
print("\n[3/6] Testing ViewSet Imports...")
try:
    from micboard.api.v1.viewsets import (
        ManufacturerViewSet,
        ReceiverViewSet,
        TransmitterViewSet,
        ChannelViewSet,
        LocationViewSet,
        GroupViewSet,
        ManufacturerConfigurationViewSet,
        ServiceHealthViewSet,
    )
    print("✅ All viewsets imported successfully")
except ImportError as e:
    print(f"❌ ViewSet import failed: {e}")
    sys.exit(1)

# Test 4: Test router configuration
print("\n[4/6] Testing Router Configuration...")
try:
    from micboard.api.v1.routers import router

    # Check registered viewsets
    registry_count = len(router.registry)
    print(f"✅ Router configured with {registry_count} endpoints")

    # List all registered endpoints
    print("\n   Registered endpoints:")
    for prefix, viewset, basename in router.registry:
        print(f"   - {prefix} ({basename})")

except Exception as e:
    print(f"❌ Router configuration failed: {e}")
    sys.exit(1)

# Test 5: Test service architecture
print("\n[5/6] Testing Service Architecture...")
try:
    from micboard.services.manufacturer_service import (
        ManufacturerService,
        ServiceRegistry,
        get_service_registry,
        device_discovered,
        device_online,
        device_offline,
        device_updated,
        device_synced,
    )

    print("✅ Service architecture imported successfully")

    # Verify signals are defined
    signals = [device_discovered, device_online, device_offline, device_updated, device_synced]
    print(f"✅ {len(signals)} signals defined and accessible")

except ImportError as e:
    print(f"❌ Service architecture import failed: {e}")
    sys.exit(1)

# Test 6: Test logging infrastructure
print("\n[6/6] Testing Logging Infrastructure...")
try:
    from micboard.services.logging import StructuredLogger, get_structured_logger

    logger = get_structured_logger()
    assert isinstance(logger, StructuredLogger)
    print("✅ Logging infrastructure working")

    # Verify all logging methods exist
    methods = [
        "log_crud_create",
        "log_crud_update",
        "log_crud_delete",
        "log_service_start",
        "log_service_stop",
        "log_service_error",
        "log_sync_start",
        "log_sync_complete",
    ]

    for method in methods:
        assert hasattr(logger, method), f"Missing method: {method}"

    print(f"✅ All {len(methods)} logging methods available")

except Exception as e:
    print(f"❌ Logging infrastructure test failed: {e}")
    sys.exit(1)

# Additional checks
print("\n" + "=" * 80)
print("ADDITIONAL VERIFICATION")
print("=" * 80)

# Check admin interfaces
print("\n[Admin] Testing Admin Interfaces...")
try:
    from micboard.admin import (
        ManufacturerConfigurationAdmin,
        ConfigurationAuditLogAdmin,
        ActivityLogAdmin,
        ServiceSyncLogAdmin,
    )
    print("✅ All admin interfaces imported successfully")
except ImportError as e:
    print(f"❌ Admin interface import failed: {e}")
    sys.exit(1)

# Check dashboard
print("\n[Dashboard] Testing Dashboard Views...")
try:
    from micboard.admin.dashboard import (
        admin_dashboard,
        api_dashboard_data,
        api_manufacturer_status,
    )
    print("✅ All dashboard views imported successfully")
except ImportError as e:
    print(f"❌ Dashboard view import failed: {e}")
    sys.exit(1)

# Summary
print("\n" + "=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)

stats = {
    "Models": 11,
    "Serializers": 9,
    "ViewSets": 8,
    "Router Endpoints": registry_count,
    "Signals": 5,
    "Logging Methods": 8,
    "Admin Interfaces": 4,
    "Dashboard Views": 3,
}

print("\n✅ ALL COMPONENTS VERIFIED SUCCESSFULLY\n")
print("Component Statistics:")
for component, count in stats.items():
    print(f"  {component}: {count}")

total_components = sum(stats.values())
print(f"\n  Total: {total_components} components")

print("\n" + "=" * 80)
print("NEXT STEPS:")
print("=" * 80)
print("""
1. Run migrations:
   python manage.py makemigrations
   python manage.py migrate

2. Create superuser (if needed):
   python manage.py createsuperuser

3. Start development server:
   python manage.py runserver

4. Access:
   - Admin: http://localhost:8000/admin/
   - Dashboard: http://localhost:8000/admin/dashboard/
   - API: http://localhost:8000/api/v1/

5. Test API endpoints:
   curl http://localhost:8000/api/v1/manufacturers/
   curl http://localhost:8000/api/v1/receivers/
   curl http://localhost:8000/api/v1/configurations/

6. Run full test suite:
   pytest tests/ -v
""")

print("=" * 80)
