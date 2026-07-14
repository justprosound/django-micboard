"""Database-backed coverage for hardware identity deduplication."""

from __future__ import annotations

import pytest

from micboard.services.deduplication.check import (
    check_api_id_conflicts,
    check_cross_vendor_api_id,
    check_device,
    find_duplicate,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_check_device_requires_manufacturer() -> None:
    with pytest.raises(ValueError, match="Manufacturer is required"):
        check_device(ip="192.0.2.80", api_device_id="device-80")


def test_check_device_reports_new_identity() -> None:
    manufacturer = ManufacturerFactory()

    result = check_device(
        serial_number="new-serial",
        mac_address="02:00:00:00:00:80",
        ip="192.0.2.80",
        api_device_id="device-80",
        manufacturer=manufacturer,
    )

    assert result.is_new is True
    assert result.existing_device is None


def test_check_device_matches_serial_number() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="serial-match",
        ip="192.0.2.81",
    )

    result = check_device(
        serial_number="serial-match",
        ip=chassis.ip,
        api_device_id="incoming-id",
        manufacturer=manufacturer,
    )

    assert result.is_duplicate is True
    assert result.existing_device == chassis
    assert result.details == {"match_type": "serial_number"}


def test_check_device_reports_serial_number_move() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="serial-moved",
        ip="192.0.2.82",
    )

    result = check_device(
        serial_number="serial-moved",
        ip="192.0.2.83",
        api_device_id="incoming-id",
        manufacturer=manufacturer,
    )

    assert result.is_moved is True
    assert result.existing_device == chassis
    assert result.details == {
        "old_ip": "192.0.2.82",
        "new_ip": "192.0.2.83",
        "match_type": "serial_number",
    }


def test_check_device_reports_cross_vendor_serial_conflict() -> None:
    existing_manufacturer = ManufacturerFactory(code="existing")
    incoming_manufacturer = ManufacturerFactory(code="incoming")
    chassis = WirelessChassisFactory(
        manufacturer=existing_manufacturer,
        serial_number="shared-serial",
        ip="192.0.2.84",
    )

    result = check_device(
        serial_number="shared-serial",
        ip=chassis.ip,
        api_device_id="incoming-id",
        manufacturer=incoming_manufacturer,
    )

    assert result.is_conflict is True
    assert result.conflict_type == "manufacturer_mismatch"
    assert result.details["existing_manufacturer"] == "existing"
    assert result.details["new_manufacturer"] == "incoming"


@pytest.mark.parametrize(
    ("incoming_ip", "expected_flag"),
    [("192.0.2.85", "is_duplicate"), ("192.0.2.86", "is_moved")],
)
def test_check_device_matches_mac_address(incoming_ip: str, expected_flag: str) -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="",
        mac_address="02:00:00:00:00:85",
        ip="192.0.2.85",
    )

    result = check_device(
        mac_address=chassis.mac_address,
        ip=incoming_ip,
        api_device_id="incoming-id",
        manufacturer=manufacturer,
    )

    assert getattr(result, expected_flag) is True
    assert result.existing_device == chassis
    assert result.details["match_type"] == "mac_address"


@pytest.mark.parametrize(
    ("identity", "expected_detail"),
    [
        ({"serial_number": "different"}, "new_serial"),
        ({"mac_address": "02:00:00:00:00:88"}, "new_mac"),
    ],
)
def test_check_device_reports_ip_identity_conflict(
    identity: dict[str, str],
    expected_detail: str,
) -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="existing",
        mac_address="02:00:00:00:00:87",
        ip="192.0.2.87",
    )

    result = check_device(
        ip=chassis.ip,
        api_device_id="incoming-id",
        manufacturer=manufacturer,
        **identity,
    )

    assert result.is_conflict is True
    assert result.conflict_type == "ip_conflict"
    assert result.details[expected_detail] == next(iter(identity.values()))


def test_check_device_matches_ip_without_stronger_identity() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(manufacturer=manufacturer, ip="192.0.2.89")

    result = check_device(
        ip=chassis.ip,
        api_device_id="incoming-id",
        manufacturer=manufacturer,
    )

    assert result.is_duplicate is True
    assert result.existing_device == chassis
    assert result.details == {"match_type": "ip"}


def test_check_device_matches_moved_api_identity() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="",
        mac_address=None,
        api_device_id="stable-api-id",
        ip="192.0.2.90",
    )

    result = check_device(
        ip="192.0.2.91",
        api_device_id="stable-api-id",
        manufacturer=manufacturer,
    )

    assert result.is_moved is True
    assert result.existing_device == chassis
    assert result.details["match_type"] == "api_device_id"


@pytest.mark.parametrize(
    ("payload", "expected_ip"),
    [
        ({"serialNumber": "lookup-serial"}, "192.0.2.92"),
        ({"macAddress": "02:00:00:00:00:93"}, "192.0.2.93"),
        ({"api_device_id": "lookup-api"}, "192.0.2.94"),
        ({"ipAddress": "192.0.2.95"}, "192.0.2.95"),
    ],
)
def test_find_duplicate_accepts_vendor_aliases(
    payload: dict[str, str],
    expected_ip: str,
) -> None:
    manufacturer = ManufacturerFactory()
    WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="lookup-serial",
        mac_address="02:00:00:00:00:93",
        api_device_id="lookup-api",
        ip=expected_ip,
    )

    duplicate = find_duplicate(payload, manufacturer)

    assert duplicate is not None
    assert duplicate.ip == expected_ip


def test_find_duplicate_returns_none_for_unknown_identity() -> None:
    manufacturer = ManufacturerFactory()

    assert find_duplicate({"id": "missing", "ip": "192.0.2.96"}, manufacturer) is None


def test_api_id_conflict_summary_returns_matching_devices() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="summary-id",
    )

    count, devices = check_api_id_conflicts("summary-id", manufacturer)

    assert count == 1
    assert devices == [(chassis.id, chassis.name, chassis.ip, chassis.serial_number)]


def test_cross_vendor_api_id_reports_only_active_other_manufacturers() -> None:
    current = ManufacturerFactory(code="current")
    active = ManufacturerFactory(code="active")
    inactive = ManufacturerFactory(code="inactive", is_active=False)
    WirelessChassisFactory(manufacturer=current, api_device_id="shared-api")
    active_chassis = WirelessChassisFactory(manufacturer=active, api_device_id="shared-api")
    WirelessChassisFactory(manufacturer=inactive, api_device_id="shared-api")

    conflicts = check_cross_vendor_api_id("shared-api", current_manufacturer=current)

    assert conflicts == [(active.code, 1, [active_chassis])]
