"""Regression tests for sensitive deduplication log data."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.deduplication.check import (
    _check_by_api_id,
    _check_by_ip,
    _check_by_mac,
    _check_by_serial,
    check_api_id_conflicts,
    check_cross_vendor_api_id,
)


def _manufacturer(*, code: str = "test-vendor", pk: int = 7) -> MagicMock:
    manufacturer = MagicMock(spec=Manufacturer)
    manufacturer.code = code
    manufacturer.id = pk
    manufacturer.pk = pk
    return manufacturer


def _existing_chassis() -> MagicMock:
    chassis = MagicMock(spec=WirelessChassis)
    chassis.pk = 42
    chassis.ip = "192.0.2.20"
    chassis.mac_address = "00:11:22:33:44:55"
    chassis.serial_number = "SERIAL-OLD"
    chassis.manufacturer = _manufacturer(code="existing-vendor", pk=8)
    chassis.manufacturer_id = 8
    return chassis


def _assert_private_values_absent(
    caplog: pytest.LogCaptureFixture,
    *private_values: str,
) -> None:
    for private_value in private_values:
        assert private_value not in caplog.text


def test_api_id_duplicate_log_excludes_identity_and_tuple_contents(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    duplicates = [
        (42, "Secret receiver one", "192.0.2.20", "SERIAL-ONE"),
        (43, "Secret receiver two", "192.0.2.21", "SERIAL-TWO"),
    ]
    queryset = MagicMock()
    queryset.values_list.return_value = duplicates

    with (
        patch.object(WirelessChassis.objects, "filter", return_value=queryset),
        caplog.at_level(logging.WARNING, logger="micboard.services.deduplication.check"),
    ):
        count, result = check_api_id_conflicts("PRIVATE-API-ID", manufacturer)

    assert (count, result) == (2, duplicates)
    assert caplog.messages == [
        "Duplicate manufacturer API identity detected "
        "(manufacturer=test-vendor, conflict=api_device_id, count=2, device_ids=[42, 43])"
    ]
    _assert_private_values_absent(
        caplog,
        "PRIVATE-API-ID",
        "Secret receiver one",
        "Secret receiver two",
        "192.0.2.20",
        "192.0.2.21",
        "SERIAL-ONE",
        "SERIAL-TWO",
    )


def test_cross_vendor_api_id_log_excludes_api_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    current_manufacturer = _manufacturer()
    other_manufacturer = _manufacturer(code="other-vendor", pk=9)
    existing = _existing_chassis()
    manufacturers = MagicMock()
    manufacturers.exclude.return_value = [other_manufacturer]
    duplicates = MagicMock()
    duplicates.count.return_value = 1
    duplicates.__iter__.return_value = iter([existing])

    with (
        patch.object(Manufacturer.objects, "filter", return_value=manufacturers),
        patch.object(WirelessChassis.objects, "filter", return_value=duplicates),
        caplog.at_level(logging.WARNING, logger="micboard.services.deduplication.check"),
    ):
        result = check_cross_vendor_api_id("PRIVATE-API-ID", current_manufacturer)

    assert result == [("other-vendor", 1, [existing])]
    assert caplog.messages == [
        "Cross-vendor API identity detected "
        "(manufacturer=other-vendor, conflict=cross_vendor_api_device_id, count=1)"
    ]
    _assert_private_values_absent(caplog, "PRIVATE-API-ID")


def test_serial_move_log_excludes_serial_and_ip_addresses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()
    existing.manufacturer = manufacturer
    existing.manufacturer_id = manufacturer.pk

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.INFO, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_serial("SERIAL-NEW", "192.0.2.30", manufacturer)

    assert result is not None
    assert result.is_moved is True
    assert caplog.messages == [
        "Device moved after deduplication match "
        "(device_id=42, manufacturer=test-vendor, match_type=serial_number)"
    ]
    _assert_private_values_absent(
        caplog,
        "SERIAL-OLD",
        "SERIAL-NEW",
        "192.0.2.20",
        "192.0.2.30",
    )


def test_serial_manufacturer_conflict_log_excludes_serial(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.WARNING, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_serial("SERIAL-NEW", "192.0.2.20", manufacturer)

    assert result is not None
    assert result.is_conflict is True
    assert caplog.messages == [
        "Device identity conflict during deduplication "
        "(device_id=42, existing_manufacturer=existing-vendor, "
        "new_manufacturer=test-vendor, match_type=serial_number, "
        "conflict=manufacturer_mismatch)"
    ]
    _assert_private_values_absent(caplog, "SERIAL-OLD", "SERIAL-NEW", "192.0.2.20")


def test_mac_move_log_excludes_network_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()
    existing.manufacturer = manufacturer
    existing.manufacturer_id = manufacturer.pk

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.INFO, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_mac(
            "AA:BB:CC:DD:EE:FF",
            "192.0.2.30",
            manufacturer,
        )

    assert result is not None
    assert result.is_moved is True
    assert result.details == {
        "old_ip": "192.0.2.20",
        "new_ip": "192.0.2.30",
        "match_type": "mac_address",
    }
    assert caplog.messages == [
        "Device moved after deduplication match "
        "(device_id=42, manufacturer=test-vendor, match_type=mac_address)"
    ]
    _assert_private_values_absent(
        caplog,
        "00:11:22:33:44:55",
        "AA:BB:CC:DD:EE:FF",
        "192.0.2.20",
        "192.0.2.30",
    )


def test_ip_serial_conflict_log_excludes_serial_and_ip_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.WARNING, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_ip(
            "192.0.2.20",
            "SERIAL-NEW",
            None,
            manufacturer,
        )

    assert result is not None
    assert result.is_conflict is True
    assert caplog.messages == [
        "Device identity conflict during deduplication "
        "(device_id=42, manufacturer=test-vendor, match_type=ip, identity=serial_number)"
    ]
    _assert_private_values_absent(caplog, "SERIAL-OLD", "SERIAL-NEW", "192.0.2.20")


def test_ip_mac_conflict_log_excludes_network_identifiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.WARNING, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_ip(
            "192.0.2.20",
            None,
            "AA:BB:CC:DD:EE:FF",
            manufacturer,
        )

    assert result is not None
    assert result.is_conflict is True
    assert result.details == {
        "existing_mac": "00:11:22:33:44:55",
        "new_mac": "AA:BB:CC:DD:EE:FF",
        "match_type": "ip",
    }
    assert caplog.messages == [
        "Device identity conflict during deduplication "
        "(device_id=42, manufacturer=test-vendor, match_type=ip, identity=mac_address)"
    ]
    _assert_private_values_absent(
        caplog,
        "00:11:22:33:44:55",
        "AA:BB:CC:DD:EE:FF",
        "192.0.2.20",
    )


def test_api_id_move_log_excludes_api_identity_and_ip_addresses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manufacturer = _manufacturer()
    existing = _existing_chassis()

    with (
        patch.object(WirelessChassis.objects, "get", return_value=existing),
        caplog.at_level(logging.INFO, logger="micboard.services.deduplication.check"),
    ):
        result = _check_by_api_id("PRIVATE-API-ID", "192.0.2.30", manufacturer)

    assert result is not None
    assert result.is_moved is True
    assert caplog.messages == [
        "Device moved after deduplication match "
        "(device_id=42, manufacturer=test-vendor, match_type=api_device_id)"
    ]
    _assert_private_values_absent(
        caplog,
        "PRIVATE-API-ID",
        "192.0.2.20",
        "192.0.2.30",
    )
