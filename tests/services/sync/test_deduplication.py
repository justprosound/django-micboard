"""Database-backed coverage for hardware identity deduplication."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from micboard.services.deduplication.check import (
    check_device,
)
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.deduplication.result import (
    DeduplicationOutcome,
    DeduplicationResult,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_check_device_requires_manufacturer() -> None:
    with pytest.raises(ValueError, match="Manufacturer is required"):
        check_device(ip="192.0.2.80", api_device_id="device-80")


def test_deduplication_result_rejects_contradictory_outcomes() -> None:
    """The outcome enum cannot express the former conflicting boolean states."""
    chassis = WirelessChassisFactory()
    with pytest.raises(PydanticValidationError, match="require an existing device"):
        DeduplicationResult(
            outcome=DeduplicationOutcome.MOVED,
            conflict_type="ip_changed",
        )
    with pytest.raises(PydanticValidationError, match="cannot reference"):
        DeduplicationResult(
            outcome=DeduplicationOutcome.NEW,
            existing_device=chassis,
        )
    with pytest.raises(PydanticValidationError, match="require a conflict type"):
        DeduplicationResult(
            outcome=DeduplicationOutcome.CONFLICT,
        )

    assert repr(DeduplicationResult.new()) == "DeduplicationResult(new_device)"
    assert "moved: ip_changed" in repr(
        DeduplicationResult.moved(chassis, conflict_type="ip_changed")
    )


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


@pytest.mark.parametrize("use_identity_index", [False, True], ids=["query", "index"])
def test_check_device_validates_every_supplied_durable_identity(
    use_identity_index: bool,
) -> None:
    """A same-vendor serial cannot hide a foreign MAC ownership conflict."""
    incoming_manufacturer = ManufacturerFactory(code="combined-incoming")
    foreign_manufacturer = ManufacturerFactory(code="combined-foreign")
    serial_owner = WirelessChassisFactory(
        manufacturer=incoming_manufacturer,
        serial_number="combined-serial",
        mac_address="02:00:00:00:00:91",
        ip="192.0.2.91",
    )
    mac_owner = WirelessChassisFactory(
        manufacturer=foreign_manufacturer,
        serial_number="foreign-combined-serial",
        mac_address="02:00:00:00:00:92",
        ip="192.0.2.92",
    )
    identity_index = None
    if use_identity_index:
        identity_index = DeviceIdentityIndex()
        identity_index.add(serial_owner)
        identity_index.add(mac_owner)

    result = check_device(
        serial_number=serial_owner.serial_number,
        mac_address=mac_owner.mac_address,
        ip="192.0.2.93",
        api_device_id="combined-incoming-device",
        manufacturer=incoming_manufacturer,
        identity_index=identity_index,
    )

    assert result.is_conflict is True
    assert result.existing_device == mac_owner
    assert result.conflict_type == "manufacturer_mismatch"
    assert result.details["match_type"] == "mac_address"


def test_check_device_rejects_durable_identities_owned_by_different_rows() -> None:
    """Two same-vendor rows cannot be merged by combining their serial and MAC."""
    manufacturer = ManufacturerFactory(code="split-identity-owner")
    serial_owner = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="split-identity-serial",
        mac_address="02:00:00:00:00:93",
        ip="192.0.2.93",
    )
    mac_owner = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="other-split-identity-serial",
        mac_address="02:00:00:00:00:94",
        ip="192.0.2.94",
    )

    result = check_device(
        serial_number=serial_owner.serial_number,
        mac_address=mac_owner.mac_address,
        ip="192.0.2.95",
        api_device_id="split-identity-device",
        manufacturer=manufacturer,
    )

    assert result.is_conflict is True
    assert result.conflict_type == "durable_identity_mismatch"
    assert result.details == {
        "serial_device_id": serial_owner.pk,
        "mac_device_id": mac_owner.pk,
    }


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("serial_number", "cross-vendor-moved-serial"),
        ("mac_address", "02:00:00:00:00:84"),
    ],
)
@pytest.mark.parametrize("use_identity_index", [False, True], ids=["query", "index"])
def test_check_device_rejects_cross_vendor_identity_at_changed_ip(
    identity_field: str,
    identity_value: str,
    use_identity_index: bool,
) -> None:
    """A foreign serial or MAC cannot be classified as an address move."""
    existing_manufacturer = ManufacturerFactory(code="existing-move-owner")
    incoming_manufacturer = ManufacturerFactory(code="incoming-move-owner")
    chassis = WirelessChassisFactory(
        manufacturer=existing_manufacturer,
        serial_number=(identity_value if identity_field == "serial_number" else ""),
        mac_address=(identity_value if identity_field == "mac_address" else None),
        ip="192.0.2.184",
    )
    identity_index = None
    if use_identity_index:
        identity_index = DeviceIdentityIndex()
        identity_index.add(chassis)

    result = check_device(
        ip="192.0.2.185",
        api_device_id="incoming-moved-id",
        manufacturer=incoming_manufacturer,
        identity_index=identity_index,
        **{identity_field: identity_value},
    )

    assert result.is_conflict is True
    assert result.is_moved is False
    assert result.is_duplicate is False
    assert result.existing_device == chassis
    assert result.conflict_type == "manufacturer_mismatch"
    assert result.details == {
        "existing_manufacturer": existing_manufacturer.code,
        "new_manufacturer": incoming_manufacturer.code,
        "match_type": identity_field,
    }
    chassis.refresh_from_db()
    assert chassis.ip == "192.0.2.184"


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("serial_number", "same-vendor-moved-serial"),
        ("mac_address", "02:00:00:00:00:86"),
    ],
)
def test_check_device_preserves_indexed_same_vendor_identity_move(
    identity_field: str,
    identity_value: str,
) -> None:
    """Vendor enforcement retains legitimate serial and MAC address moves."""
    manufacturer = ManufacturerFactory(code="same-move-owner")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number=(identity_value if identity_field == "serial_number" else ""),
        mac_address=(identity_value if identity_field == "mac_address" else None),
        ip="192.0.2.186",
    )
    identity_index = DeviceIdentityIndex()
    identity_index.add(chassis)

    result = check_device(
        ip="192.0.2.187",
        api_device_id="same-owner-moved-id",
        manufacturer=manufacturer,
        identity_index=identity_index,
        **{identity_field: identity_value},
    )

    assert result.is_moved is True
    assert result.is_conflict is False
    assert result.existing_device == chassis
    assert result.details == {
        "old_ip": "192.0.2.186",
        "new_ip": "192.0.2.187",
        "match_type": identity_field,
    }


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


@pytest.mark.parametrize("use_identity_index", [False, True], ids=["query", "index"])
@pytest.mark.parametrize("same_vendor", [False, True], ids=["cross-vendor", "same-vendor"])
def test_check_device_canonicalizes_legacy_mac_variants_at_changed_ip(
    use_identity_index: bool,
    same_vendor: bool,
) -> None:
    """Case and delimiter variants retain ownership semantics on every lookup path."""
    existing_manufacturer = ManufacturerFactory(code="legacy-mac-owner")
    incoming_manufacturer = (
        existing_manufacturer if same_vendor else ManufacturerFactory(code="incoming-mac-owner")
    )
    chassis = WirelessChassisFactory(
        manufacturer=existing_manufacturer,
        serial_number="",
        mac_address="AA-BB-CC-DD-EE-FF",
        ip="192.0.2.197",
    )
    identity_index = None
    if use_identity_index:
        identity_index = DeviceIdentityIndex.build(
            [
                SimpleNamespace(
                    serial_number="",
                    mac_address="aabbccddeeff",
                    ip="192.0.2.198",
                    api_device_id="incoming-mac-id",
                )
            ],
            manufacturer=incoming_manufacturer,
        )

    result = check_device(
        mac_address="aabbccddeeff",
        ip="192.0.2.198",
        api_device_id="incoming-mac-id",
        manufacturer=incoming_manufacturer,
        identity_index=identity_index,
    )

    assert result.existing_device == chassis
    assert result.details["match_type"] == "mac_address"
    assert result.is_moved is same_vendor
    assert result.is_conflict is not same_vendor


def test_check_device_ip_comparison_uses_canonical_mac_identity() -> None:
    """An indexed IP match does not conflict solely because MAC formatting changed."""
    manufacturer = ManufacturerFactory(code="canonical-ip-owner")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="",
        mac_address="AA-BB-CC-DD-EE-FF",
        ip="192.0.2.199",
    )
    identity_index = DeviceIdentityIndex(by_ip={chassis.ip: [chassis]})

    result = check_device(
        mac_address="aa:bb:cc:dd:ee:ff",
        ip=chassis.ip,
        api_device_id="different-api-id",
        manufacturer=manufacturer,
        identity_index=identity_index,
    )

    assert result.is_duplicate is True
    assert result.is_conflict is False
    assert result.details == {"match_type": "ip"}


def test_invalid_mac_placeholders_are_not_hardware_identity() -> None:
    """Two vendor placeholders cannot merge otherwise distinct chassis."""
    manufacturer = ManufacturerFactory(code="placeholder-mac-owner")
    existing = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="first-serial",
        mac_address="unknown",
        ip="192.0.2.201",
    )

    result = check_device(
        serial_number="second-serial",
        mac_address="unknown",
        ip="192.0.2.202",
        api_device_id="second-api-id",
        manufacturer=manufacturer,
    )

    assert result.is_new is True
    assert result.existing_device is None
    existing.refresh_from_db()
    assert str(existing.ip) == "192.0.2.201"


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
