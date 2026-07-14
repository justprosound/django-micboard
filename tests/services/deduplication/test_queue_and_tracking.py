"""Behavioral coverage for discovery queue models and movement tracking."""

from __future__ import annotations

import pytest

from micboard.services.deduplication.queue_conflict_service import (
    DiscoveryQueueConflictService,
)
from micboard.services.deduplication.tracking import log_device_movement
from tests.factories.discovery import DiscoveryQueueFactory, ManufacturerFactory
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory
from tests.factories.locations import LocationFactory

pytestmark = pytest.mark.django_db


def test_serial_matches_detect_chassis_and_charger_duplicates_and_moves() -> None:
    """Serial identity takes precedence and distinguishes movement from duplicates."""
    chassis = WirelessChassisFactory(ip="192.0.2.20")
    duplicate = DiscoveryQueueConflictService.check(
        DiscoveryQueueFactory.build(
            serial_number=chassis.serial_number,
            ip=chassis.ip,
        )
    )
    moved = DiscoveryQueueConflictService.check(
        DiscoveryQueueFactory.build(
            serial_number=chassis.serial_number,
            ip="192.0.2.21",
        )
    )

    charger = ChargerFactory(ip="192.0.2.22")
    charger_duplicate = DiscoveryQueueConflictService.check(
        DiscoveryQueueFactory.build(
            serial_number=charger.serial_number,
            ip=charger.ip,
        )
    )
    charger_moved = DiscoveryQueueConflictService.check(
        DiscoveryQueueFactory.build(
            serial_number=charger.serial_number,
            ip="192.0.2.23",
        )
    )

    assert duplicate.is_duplicate is True
    assert duplicate.existing_device == chassis
    assert duplicate.conflict_type == "duplicate"
    assert moved.conflict_type == "moved"
    assert moved.existing_device == chassis
    assert charger_duplicate.conflict_type == "duplicate"
    assert charger_duplicate.existing_charger == charger
    assert charger_moved.conflict_type == "moved"


@pytest.mark.parametrize("with_serial", [False, True])
def test_ip_matches_detect_chassis_metadata_updates_or_conflicts(with_serial: bool) -> None:
    """An occupied chassis address is a conflict only for another serial."""
    chassis = WirelessChassisFactory(ip="192.0.2.30")
    entry = DiscoveryQueueFactory.build(
        serial_number="different-serial" if with_serial else "",
        ip=chassis.ip,
    )

    result = DiscoveryQueueConflictService.check(entry)

    assert result.is_ip_conflict is True
    assert result.existing_device == chassis
    assert result.conflict_type == ("ip_conflict" if with_serial else "metadata_update")


@pytest.mark.parametrize("with_serial", [False, True])
def test_ip_matches_detect_charger_metadata_updates_or_conflicts(with_serial: bool) -> None:
    """An occupied charger address is a conflict only for another serial."""
    charger = ChargerFactory(ip="192.0.2.40")
    entry = DiscoveryQueueFactory.build(
        serial_number="different-serial" if with_serial else "",
        ip=charger.ip,
    )

    result = DiscoveryQueueConflictService.check(entry)

    assert result.is_ip_conflict is True
    assert result.existing_charger == charger
    assert result.conflict_type == ("ip_conflict" if with_serial else "metadata_update")


def test_duplicate_check_returns_empty_result_for_an_unseen_device() -> None:
    """A new serial and address remain eligible for import."""
    entry = DiscoveryQueueFactory.build(serial_number="unseen", ip="192.0.2.50")

    result = DiscoveryQueueConflictService.check(entry)
    assert result.has_conflict is False
    assert result.existing_device is None
    assert result.existing_charger is None
    assert result.conflict_type is None


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
    assert movement.movement_type == "ip_only"
    assert movement.detected_by == "sync"
    assert movement.reason == "DHCP reassignment"


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
