#!/usr/bin/env python
"""Test script for device lifecycle signal handlers.

Tests that signals properly create ActivityLog entries and update device status.

Usage:
    python scripts/test_signal_handlers.py
"""

import os
import sys

import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from micboard.models import ActivityLog, Manufacturer, WirelessChassis
from micboard.services.manufacturer_service import (
    device_discovered,
    device_offline,
    device_online,
    device_synced,
    device_updated,
)


def test_device_discovered():
    """Test device discovery signal."""
    print("\n=== Testing device_discovered signal ===")

    initial_count = ActivityLog.objects.count()

    # Emit signal
    device_discovered.send(
        sender=None,
        service_code="shure",
        device_data={
            "id": "test-receiver-001",
            "name": "Test WirelessChassis",
            "type": "receiver",
            "model": "ULXD4D",
            "ip_address": "172.21.10.100",
        },
    )

    # Check ActivityLog created
    new_count = ActivityLog.objects.count()
    if new_count > initial_count:
        latest_log = ActivityLog.objects.latest("created_at")
        print(f"✓ ActivityLog created: {latest_log.summary}")
        print(f"  Activity type: {latest_log.activity_type}")
        print(f"  Status: {latest_log.status}")
        print(f"  Details: {latest_log.details}")
        return True
    else:
        print("✗ No ActivityLog entry created")
        return False


def test_device_online():
    """Test device online signal with existing receiver."""
    print("\n=== Testing device_online signal ===")

    # Get or create a manufacturer
    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={"name": "Shure", "api_type": "system_api"},
    )

    # Get or create a receiver
    receiver, created = WirelessChassis.objects.get_or_create(
        manufacturer=manufacturer,
        api_device_id="test-receiver-001",
        defaults={
            "name": "Test WirelessChassis 001",
            "device_type": "ulxd",
            "ip": "172.21.10.100",
            "is_active": False,
        },
    )

    print(f"WirelessChassis initial status: is_active={receiver.is_active}")

    initial_count = ActivityLog.objects.count()

    # Emit signal
    device_online.send(
        sender=None,
        service_code="shure",
        device_id="test-receiver-001",
        device_type="receiver",
    )

    # Refresh receiver from DB
    receiver.refresh_from_db()

    # Check status updated
    if receiver.is_active:
        print(f"✓ WirelessChassis status updated: is_active={receiver.is_active}")
    else:
        print(f"✗ WirelessChassis status not updated: is_active={receiver.is_active}")

    # Check ActivityLog created
    new_count = ActivityLog.objects.count()
    if new_count > initial_count:
        latest_log = ActivityLog.objects.latest("created_at")
        print(f"✓ ActivityLog created: {latest_log.summary}")
        return receiver.is_active
    else:
        print("✗ No ActivityLog entry created")
        return False


def test_device_offline():
    """Test device offline signal."""
    print("\n=== Testing device_offline signal ===")

    manufacturer = Manufacturer.objects.get(code="shure")
    receiver = WirelessChassis.objects.get(
        manufacturer=manufacturer,
        api_device_id="test-receiver-001",
    )

    # Ensure receiver is online first
    receiver.is_active = True
    receiver.save()
    print(f"WirelessChassis initial status: is_active={receiver.is_active}")

    initial_count = ActivityLog.objects.count()

    # Emit signal
    device_offline.send(
        sender=None,
        service_code="shure",
        device_id="test-receiver-001",
        device_type="receiver",
    )

    # Refresh receiver from DB
    receiver.refresh_from_db()

    # Check status updated
    if not receiver.is_active:
        print(f"✓ WirelessChassis status updated: is_active={receiver.is_active}")
    else:
        print(f"✗ WirelessChassis status not updated: is_active={receiver.is_active}")

    # Check ActivityLog created
    new_count = ActivityLog.objects.count()
    if new_count > initial_count:
        latest_log = ActivityLog.objects.latest("created_at")
        print(f"✓ ActivityLog created: {latest_log.summary}")
        return not receiver.is_active
    else:
        print("✗ No ActivityLog entry created")
        return False


def test_device_updated():
    """Test device data update signal."""
    print("\n=== Testing device_updated signal ===")

    initial_count = ActivityLog.objects.count()

    # Emit signal
    device_updated.send(
        sender=None,
        service_code="shure",
        device_id="test-receiver-001",
        device_type="receiver",
        old_data={
            "ip_address": "172.21.10.100",
            "firmware": "1.0.0",
            "battery_level": 80,
        },
        new_data={
            "ip_address": "172.21.10.101",  # Changed
            "firmware": "1.0.1",  # Changed
            "battery_level": 80,  # Same
        },
    )

    # Check ActivityLog created
    new_count = ActivityLog.objects.count()
    if new_count > initial_count:
        latest_log = ActivityLog.objects.latest("created_at")
        print(f"✓ ActivityLog created: {latest_log.summary}")
        print(f"  Changed fields: {latest_log.details.get('changed_fields', {}).keys()}")
        return True
    else:
        print("✗ No ActivityLog entry created")
        return False


def test_device_synced():
    """Test sync completion signal."""
    print("\n=== Testing device_synced signal ===")

    initial_count = ActivityLog.objects.count()

    # Emit signal
    device_synced.send(
        sender=None,
        service_code="shure",
        sync_result={
            "device_count": 15,
            "online_count": 12,
            "error_count": 0,
            "status": "success",
            "duration_seconds": 2.5,
        },
    )

    # Check ActivityLog created
    new_count = ActivityLog.objects.count()
    if new_count > initial_count:
        latest_log = ActivityLog.objects.latest("created_at")
        print(f"✓ ActivityLog created: {latest_log.summary}")
        print(f"  Status: {latest_log.status}")
        print(f"  Details: {latest_log.details}")
        return True
    else:
        print("✗ No ActivityLog entry created")
        return False


def main():
    """Run all signal tests."""
    print("=" * 60)
    print("Testing WirelessChassis Lifecycle Signal Handlers")
    print("=" * 60)

    results = {
        "device_discovered": test_device_discovered(),
        "device_online": test_device_online(),
        "device_offline": test_device_offline(),
        "device_updated": test_device_updated(),
        "device_synced": test_device_synced(),
    }

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    # Show recent ActivityLog entries
    print("\n" + "=" * 60)
    print("Recent ActivityLog Entries (last 10)")
    print("=" * 60)

    recent_logs = ActivityLog.objects.order_by("-created_at")[:10]
    for log in recent_logs:
        print(f"\n[{log.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {log.activity_type}")
        print(f"  Operation: {log.operation}")
        print(f"  Summary: {log.summary}")
        print(f"  Status: {log.status}")

    # Overall result
    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        failed_count = sum(1 for v in results.values() if not v)
        print(f"✗ {failed_count} TEST(S) FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
