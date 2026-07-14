"""Behavioral coverage for discovery review and movement tracking."""

from __future__ import annotations

import pytest

from micboard.services.deduplication.queue import get_pending_approvals, queue_for_approval
from micboard.services.deduplication.result import DeduplicationResult
from micboard.services.deduplication.tracking import (
    get_unacknowledged_movements,
    log_device_movement,
)
from tests.factories.discovery import DiscoveryQueueFactory, ManufacturerFactory
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory
from tests.factories.locations import LocationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("api_data", "result", "expected"),
    [
        (
            {
                "serial_number": "serial-snake",
                "api_device_id": "device-snake",
                "ip": "192.0.2.10",
                "device_type": "receiver",
                "name": "Snake Case",
                "firmware_version": "1.0",
            },
            DeduplicationResult(is_conflict=True),
            ("pending", False, True),
        ),
        (
            {
                "serialNumber": "serial-camel",
                "id": "device-camel",
                "ipAddress": "192.0.2.11",
                "model": "transmitter",
                "name": "Camel Case",
                "firmware": "2.0",
            },
            DeduplicationResult(is_duplicate=True),
            ("duplicate", True, False),
        ),
        (
            {"id": "device-moved", "ip": "192.0.2.12"},
            DeduplicationResult(is_moved=True),
            ("pending", True, False),
        ),
    ],
)
def test_queue_for_approval_normalizes_payload_and_deduplication_state(
    api_data: dict[str, str],
    result: DeduplicationResult,
    expected: tuple[str, bool, bool],
) -> None:
    """Manufacturer payload aliases become a stable review queue record."""
    entry = queue_for_approval(
        manufacturer=ManufacturerFactory(),
        api_data=api_data,
        dedup_result=result,
    )

    assert (entry.status, entry.is_duplicate, entry.is_ip_conflict) == expected
    assert entry.metadata == api_data
    assert entry.api_device_id == api_data.get("api_device_id", api_data.get("id", ""))
    assert entry.device_type == api_data.get("device_type", api_data.get("model", "unknown"))


def test_pending_approval_queries_can_be_scoped_to_manufacturer() -> None:
    """Review lists contain pending records only and honor manufacturer scope."""
    selected = ManufacturerFactory()
    pending = DiscoveryQueueFactory(manufacturer=selected, status="pending")
    other = DiscoveryQueueFactory(status="pending")
    DiscoveryQueueFactory(manufacturer=selected, status="approved")

    assert get_pending_approvals(selected) == [pending]
    assert set(get_pending_approvals()) == {pending, other}


def test_serial_matches_detect_chassis_and_charger_duplicates_and_moves() -> None:
    """Serial identity takes precedence and distinguishes movement from duplicates."""
    chassis = WirelessChassisFactory(ip="192.0.2.20")
    duplicate = DiscoveryQueueFactory.build(
        serial_number=chassis.serial_number,
        ip=chassis.ip,
    ).check_for_duplicates()
    moved = DiscoveryQueueFactory.build(
        serial_number=chassis.serial_number,
        ip="192.0.2.21",
    ).check_for_duplicates()

    charger = ChargerFactory(ip="192.0.2.22")
    charger_duplicate = DiscoveryQueueFactory.build(
        serial_number=charger.serial_number,
        ip=charger.ip,
    ).check_for_duplicates()
    charger_moved = DiscoveryQueueFactory.build(
        serial_number=charger.serial_number,
        ip="192.0.2.23",
    ).check_for_duplicates()

    assert duplicate == {
        "is_duplicate": True,
        "is_ip_conflict": False,
        "existing_device": chassis,
        "existing_charger": None,
        "conflict_type": "duplicate",
    }
    assert moved["conflict_type"] == "moved"
    assert moved["existing_device"] == chassis
    assert charger_duplicate["conflict_type"] == "duplicate"
    assert charger_duplicate["existing_charger"] == charger
    assert charger_moved["conflict_type"] == "moved"


@pytest.mark.parametrize("with_serial", [False, True])
def test_ip_matches_detect_chassis_metadata_updates_or_conflicts(with_serial: bool) -> None:
    """An occupied chassis address is a conflict only for another serial."""
    chassis = WirelessChassisFactory(ip="192.0.2.30")
    entry = DiscoveryQueueFactory.build(
        serial_number="different-serial" if with_serial else "",
        ip=chassis.ip,
    )

    result = entry.check_for_duplicates()

    assert result["is_ip_conflict"] is True
    assert result["existing_device"] == chassis
    assert result["conflict_type"] == ("ip_conflict" if with_serial else "metadata_update")


@pytest.mark.parametrize("with_serial", [False, True])
def test_ip_matches_detect_charger_metadata_updates_or_conflicts(with_serial: bool) -> None:
    """An occupied charger address is a conflict only for another serial."""
    charger = ChargerFactory(ip="192.0.2.40")
    entry = DiscoveryQueueFactory.build(
        serial_number="different-serial" if with_serial else "",
        ip=charger.ip,
    )

    result = entry.check_for_duplicates()

    assert result["is_ip_conflict"] is True
    assert result["existing_charger"] == charger
    assert result["conflict_type"] == ("ip_conflict" if with_serial else "metadata_update")


def test_duplicate_check_returns_empty_result_for_an_unseen_device() -> None:
    """A new serial and address remain eligible for import."""
    entry = DiscoveryQueueFactory.build(serial_number="unseen", ip="192.0.2.50")

    assert entry.check_for_duplicates() == {
        "is_duplicate": False,
        "is_ip_conflict": False,
        "existing_device": None,
        "existing_charger": None,
        "conflict_type": None,
    }


def test_queue_string_distinguishes_serial_and_address_identity() -> None:
    """Review labels expose the strongest available device identity."""
    serial_entry = DiscoveryQueueFactory.build(name="Receiver", serial_number="ABC")
    address_entry = DiscoveryQueueFactory.build(name="Receiver", serial_number="")

    assert str(serial_entry) == "Receiver (S/N: ABC) - Pending Review"
    assert str(address_entry) == f"Receiver @ {address_entry.ip} - Pending Review"


def test_movement_logging_and_queries_preserve_audit_context() -> None:
    """Movement creation records details and pending queries support manufacturer scope."""
    selected = ManufacturerFactory()
    chassis = WirelessChassisFactory(manufacturer=selected)
    movement = log_device_movement(
        chassis,
        old_ip="192.0.2.60",
        new_ip="192.0.2.61",
        detected_by="sync",
        reason="DHCP reassignment",
    )
    other = log_device_movement(WirelessChassisFactory())
    acknowledged = log_device_movement(WirelessChassisFactory(manufacturer=selected))
    acknowledged.acknowledged = True
    acknowledged.save(update_fields=["acknowledged"])

    assert movement.movement_type == "ip_only"
    assert movement.detected_by == "sync"
    assert movement.reason == "DHCP reassignment"
    assert get_unacknowledged_movements(selected) == [movement]
    assert set(get_unacknowledged_movements()) == {movement, other}


def test_movement_type_and_label_cover_location_and_no_change_states() -> None:
    """Audit labels describe combined, location-only, and empty changes."""
    old_location = LocationFactory(name="Studio A")
    new_location = LocationFactory(name="Studio B")
    chassis = WirelessChassisFactory(name="Receiver")

    combined = log_device_movement(
        chassis,
        old_ip="192.0.2.70",
        new_ip="192.0.2.71",
        old_location=old_location,
        new_location=new_location,
    )
    location_only = log_device_movement(
        chassis,
        old_location=old_location,
        new_location=new_location,
    )
    unchanged = log_device_movement(chassis, old_ip="192.0.2.72", new_ip="192.0.2.72")

    assert combined.movement_type == "ip_and_location"
    assert "IP: 192.0.2.70 → 192.0.2.71, Location: Studio A → Studio B" in str(combined)
    assert location_only.movement_type == "location_only"
    assert "Location: Studio A → Studio B" in str(location_only)
    assert unchanged.movement_type == "unknown"
    assert "No changes" in str(unchanged)
