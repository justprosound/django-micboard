#!/usr/bin/env python
"""Test script for device deduplication service.

Tests:
1. New device detection
2. Duplicate device detection (by serial number)
3. WirelessChassis movement detection (IP change)
4. IP conflict detection (different device, same IP)
5. MAC address matching
"""

import os
import sys

import django

# Setup Django - ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from micboard.models import Manufacturer, WirelessChassis
from micboard.services.deduplication_service import get_deduplication_service


def test_new_device():
    """Test detection of new device."""
    print("\n=== Test 1: New WirelessChassis Detection ===")

    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={
            "name": "Shure Incorporated",
            "api_type": "rest",
        },
    )

    dedup_service = get_deduplication_service(manufacturer)
    result = dedup_service.check_device(
        serial_number="TEST-001",
        mac_address="00:11:22:33:44:55",
        ip="192.168.1.100",
        api_device_id="test-device-1",
        manufacturer=manufacturer,
    )

    print(f"  Is New: {result.is_new}")
    print(f"  Is Duplicate: {result.is_duplicate}")
    print(f"  Is Moved: {result.is_moved}")
    print(f"  Is Conflict: {result.is_conflict}")
    assert result.is_new, "Expected new device"
    print("  ✓ PASSED")


def test_duplicate_by_serial():
    """Test detection of duplicate by serial number."""
    print("\n=== Test 2: Duplicate Detection (Serial Number) ===")

    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={
            "name": "Shure Incorporated",
            "api_type": "rest",
        },
    )

    # Create receiver
    receiver = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="test-device-2",
        serial_number="TEST-002",
        mac_address="00:11:22:33:44:66",
        ip="192.168.1.101",
        name="Test WirelessChassis 2",
    )

    dedup_service = get_deduplication_service(manufacturer)
    result = dedup_service.check_device(
        serial_number="TEST-002",  # Same serial
        mac_address="00:11:22:33:44:66",
        ip="192.168.1.101",
        api_device_id="test-device-2",
        manufacturer=manufacturer,
    )

    print(f"  Is New: {result.is_new}")
    print(f"  Is Duplicate: {result.is_duplicate}")
    print(f"  Existing WirelessChassis: {result.existing_device}")
    assert result.is_duplicate, "Expected duplicate"
    assert result.existing_device == receiver, "Should match existing receiver"
    print("  ✓ PASSED")


def test_device_movement():
    """Test detection of device IP movement."""
    print("\n=== Test 3: WirelessChassis Movement Detection (IP Change) ===")

    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={
            "name": "Shure Incorporated",
            "api_type": "rest",
        },
    )

    # Create receiver with specific IP
    receiver = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="test-device-3",
        serial_number="TEST-003",
        mac_address="00:11:22:33:44:77",
        ip="192.168.1.102",
        name="Test WirelessChassis 3",
    )

    dedup_service = get_deduplication_service(manufacturer)
    result = dedup_service.check_device(
        serial_number="TEST-003",  # Same serial
        mac_address="00:11:22:33:44:77",  # Same MAC
        ip="192.168.1.200",  # Different IP!
        api_device_id="test-device-3",
        manufacturer=manufacturer,
    )

    print(f"  Is New: {result.is_new}")
    print(f"  Is Moved: {result.is_moved}")
    print(f"  Conflict Type: {result.conflict_type}")
    print(f"  Old IP: {result.existing_device.ip if result.existing_device else 'N/A'}")
    print("  New IP: 192.168.1.200")
    assert result.is_moved, "Expected device movement"
    assert result.conflict_type == "ip_changed", "Should detect IP change"
    print("  ✓ PASSED")


def test_ip_conflict():
    """Test detection of IP conflict (different device, same IP)."""
    print("\n=== Test 4: IP Conflict Detection ===")

    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={
            "name": "Shure Incorporated",
            "api_type": "rest",
        },
    )

    # Create receiver with specific IP
    existing_receiver = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="test-device-4",
        serial_number="TEST-004",
        mac_address="00:11:22:33:44:88",
        ip="192.168.1.103",
        name="Test WirelessChassis 4",
    )

    dedup_service = get_deduplication_service(manufacturer)
    result = dedup_service.check_device(
        serial_number="TEST-005",  # Different serial!
        mac_address="00:11:22:33:44:99",  # Different MAC!
        ip="192.168.1.103",  # Same IP as existing device
        api_device_id="test-device-5",
        manufacturer=manufacturer,
    )

    print(f"  Is Conflict: {result.is_conflict}")
    print(f"  Conflict Type: {result.conflict_type}")
    print(
        f"  Existing WirelessChassis: {result.existing_device.serial_number if result.existing_device else 'N/A'}"
    )
    print("  New WirelessChassis Serial: TEST-005")
    assert result.is_conflict, "Expected IP conflict"
    assert result.conflict_type == "ip_conflict", "Should detect IP conflict"
    print("  ✓ PASSED")


def test_mac_address_matching():
    """Test matching by MAC address when serial is missing."""
    print("\n=== Test 5: MAC Address Matching ===")

    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure",
        defaults={
            "name": "Shure Incorporated",
            "api_type": "rest",
        },
    )

    # Create receiver with MAC but no serial
    receiver = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="test-device-6",
        serial_number="",  # No serial
        mac_address="00:11:22:33:44:AA",
        ip="192.168.1.104",
        name="Test WirelessChassis 6",
    )

    dedup_service = get_deduplication_service(manufacturer)
    result = dedup_service.check_device(
        serial_number=None,  # No serial provided
        mac_address="00:11:22:33:44:AA",  # Same MAC
        ip="192.168.1.104",
        api_device_id="test-device-6",
        manufacturer=manufacturer,
    )

    print(f"  Is Duplicate: {result.is_duplicate}")
    print("  Matched By: MAC Address")
    print(f"  Existing WirelessChassis: {result.existing_device}")
    assert result.is_duplicate, "Expected duplicate match by MAC"
    assert result.existing_device == receiver, "Should match by MAC address"
    print("  ✓ PASSED")


def cleanup_test_data():
    """Remove test receivers."""
    print("\n=== Cleaning Up Test Data ===")
    deleted_count, _ = WirelessChassis.objects.filter(serial_number__startswith="TEST-").delete()
    print(f"  Deleted {deleted_count} test receiver(s)")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("WirelessChassis Deduplication Service Test Suite")
    print("=" * 60)

    try:
        cleanup_test_data()  # Clean up any previous test data

        test_new_device()
        test_duplicate_by_serial()
        test_device_movement()
        test_ip_conflict()
        test_mac_address_matching()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60 + "\n")

        cleanup_test_data()  # Clean up after tests

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)
