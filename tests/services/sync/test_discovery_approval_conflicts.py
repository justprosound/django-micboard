"""Regression coverage for conflicting discovery approval identities."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError

import pytest

from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.discovery_approval_service import (
    DiscoveryApprovalResult,
    DiscoveryApprovalService,
)
from tests.factories.base import UserFactory
from tests.factories.discovery import DiscoveryQueueFactory
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _reviewer() -> Any:
    """Create a reviewer with all inventory permissions."""
    return UserFactory(is_staff=True, is_superuser=True)


def _approve(reviewer: Any, *items: DiscoveryQueue) -> DiscoveryApprovalResult:
    """Approve only the supplied queue records."""
    return DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk__in=[item.pk for item in items]),
        reviewer=reviewer,
    )


def _assert_pending(items: Iterable[DiscoveryQueue]) -> None:
    """Assert rejected records retain their untouched review state."""
    for item in items:
        item.refresh_from_db()
        assert item.status == "pending"
        assert item.reviewed_by is None
        assert item.reviewed_at is None
        assert item.existing_device is None
        assert item.existing_charger is None


def test_same_api_identity_with_different_ips_rejects_entire_batch() -> None:
    """One manufacturer/API identity cannot resolve to two addresses at once."""
    reviewer = _reviewer()
    first_item = DiscoveryQueueFactory(
        api_device_id="shared-api-id",
        serial_number="api-conflict-one",
        ip="192.0.2.131",
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=first_item.manufacturer,
        api_device_id=first_item.api_device_id,
        serial_number="api-conflict-two",
        ip="192.0.2.132",
    )
    chassis_count = WirelessChassis.objects.count()

    with pytest.raises(ValidationError):
        _approve(reviewer, first_item, second_item)

    _assert_pending((first_item, second_item))
    assert WirelessChassis.objects.count() == chassis_count


def test_same_serial_with_different_api_ids_rejects_entire_batch() -> None:
    """One manufacturer/serial identity cannot create two managed chassis."""
    reviewer = _reviewer()
    first_item = DiscoveryQueueFactory(
        api_device_id="serial-conflict-api-one",
        serial_number="shared-serial",
        ip="192.0.2.133",
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=first_item.manufacturer,
        api_device_id="serial-conflict-api-two",
        serial_number=first_item.serial_number,
        ip="192.0.2.134",
    )
    chassis_count = WirelessChassis.objects.count()

    with pytest.raises(ValidationError):
        _approve(reviewer, first_item, second_item)

    _assert_pending((first_item, second_item))
    assert WirelessChassis.objects.count() == chassis_count


def test_chassis_approval_rejects_ip_owned_by_charger() -> None:
    """Wireless inventory must not adopt an address assigned to a charger."""
    reviewer = _reviewer()
    charger = ChargerFactory(ip="192.0.2.135")
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        api_device_id="charger-owned-ip",
        serial_number="new-chassis-serial",
        ip=charger.ip,
        device_type="receiver",
    )
    chassis_count = WirelessChassis.objects.count()
    original_charger = (charger.ip, charger.status, charger.serial_number)

    with pytest.raises(ValidationError):
        _approve(reviewer, queue_item)

    _assert_pending((queue_item,))
    charger.refresh_from_db()
    assert WirelessChassis.objects.count() == chassis_count
    assert (charger.ip, charger.status, charger.serial_number) == original_charger


def test_charger_approval_rejects_ip_owned_by_wireless_chassis() -> None:
    """Charger inventory must not adopt an address assigned to a chassis."""
    reviewer = _reviewer()
    charger = ChargerFactory(ip="192.0.2.136")
    chassis = WirelessChassisFactory(
        manufacturer=charger.manufacturer,
        ip="192.0.2.137",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number=charger.serial_number,
        ip=chassis.ip,
        device_type="charger",
    )
    original_charger = (charger.ip, charger.status, charger.name)
    chassis_count = WirelessChassis.objects.count()

    with pytest.raises(ValidationError):
        _approve(reviewer, queue_item)

    _assert_pending((queue_item,))
    charger.refresh_from_db()
    assert (charger.ip, charger.status, charger.name) == original_charger
    assert WirelessChassis.objects.count() == chassis_count


def test_blank_serial_does_not_implicitly_select_blank_serial_charger() -> None:
    """Missing charger identity must not match an arbitrary blank-serial row."""
    reviewer = _reviewer()
    charger = ChargerFactory(
        serial_number="",
        ip="192.0.2.138",
        status="discovered",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number="",
        ip="192.0.2.139",
        device_type="charger",
        existing_charger=None,
    )
    original_charger = (charger.ip, charger.status, charger.name)

    with pytest.raises(ValidationError):
        _approve(reviewer, queue_item)

    _assert_pending((queue_item,))
    charger.refresh_from_db()
    assert (charger.ip, charger.status, charger.name) == original_charger
    assert Charger.objects.filter(manufacturer=charger.manufacturer).count() == 1


def test_same_manufacturer_ip_match_cannot_take_over_unlinked_chassis() -> None:
    """An IP match alone must not authorize replacing a chassis identity."""
    reviewer = _reviewer()
    chassis = WirelessChassisFactory(
        api_device_id="established-api-id",
        serial_number="established-serial",
        ip="192.0.2.141",
        status="discovered",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=chassis.manufacturer,
        api_device_id="different-api-id",
        serial_number="different-serial",
        ip=chassis.ip,
        existing_device=None,
    )
    original_chassis = (
        chassis.api_device_id,
        chassis.serial_number,
        chassis.ip,
        chassis.status,
    )

    with pytest.raises(ValidationError):
        _approve(reviewer, queue_item)

    _assert_pending((queue_item,))
    chassis.refresh_from_db()
    assert (
        chassis.api_device_id,
        chassis.serial_number,
        chassis.ip,
        chassis.status,
    ) == original_chassis


def test_same_charger_cannot_receive_two_ips_in_one_batch() -> None:
    """Two queue rows cannot move one charger to conflicting addresses."""
    reviewer = _reviewer()
    charger = ChargerFactory(
        ip="192.0.2.142",
        status="discovered",
    )
    first_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number=charger.serial_number,
        ip="192.0.2.143",
        device_type="charger",
        existing_charger=None,
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number=charger.serial_number,
        ip="192.0.2.144",
        device_type="charger",
        existing_charger=None,
    )
    original_charger = (charger.ip, charger.status, charger.name)

    with pytest.raises(ValidationError):
        _approve(reviewer, first_item, second_item)

    _assert_pending((first_item, second_item))
    charger.refresh_from_db()
    assert (charger.ip, charger.status, charger.name) == original_charger
    assert Charger.objects.filter(pk=charger.pk).count() == 1


def test_mixed_hardware_cannot_claim_same_free_ip_in_one_batch() -> None:
    """Charger and chassis approvals cannot share one newly assigned address."""
    reviewer = _reviewer()
    charger = ChargerFactory(
        ip="192.0.2.145",
        status="discovered",
    )
    shared_ip = "192.0.2.146"
    charger_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number=charger.serial_number,
        ip=shared_ip,
        device_type="charger",
        existing_charger=None,
    )
    chassis_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        api_device_id="mixed-batch-chassis",
        serial_number="mixed-batch-chassis-serial",
        ip=shared_ip,
        device_type="receiver",
        existing_device=None,
    )
    original_charger = (charger.ip, charger.status, charger.name)
    chassis_count = WirelessChassis.objects.count()

    with pytest.raises(ValidationError):
        _approve(reviewer, charger_item, chassis_item)

    _assert_pending((charger_item, chassis_item))
    charger.refresh_from_db()
    assert (charger.ip, charger.status, charger.name) == original_charger
    assert WirelessChassis.objects.count() == chassis_count
    assert not WirelessChassis.objects.filter(ip=shared_ip).exists()


def test_max_length_serial_generates_bounded_api_identity() -> None:
    """A serial fallback must fit the managed chassis API-ID column."""
    reviewer = _reviewer()
    serial_number = "s" * 100
    queue_item = DiscoveryQueueFactory(
        api_device_id="",
        serial_number=serial_number,
        ip="192.0.2.140",
    )

    result = _approve(reviewer, queue_item)

    queue_item.refresh_from_db()
    chassis = queue_item.existing_device
    assert chassis is not None
    api_id_max_length = WirelessChassis._meta.get_field("api_device_id").max_length
    assert api_id_max_length is not None
    assert 0 < len(chassis.api_device_id) <= api_id_max_length
    assert result.model_dump() == {
        "imported_count": 1,
        "created_count": 1,
        "updated_count": 0,
    }
    assert chassis.serial_number == serial_number
