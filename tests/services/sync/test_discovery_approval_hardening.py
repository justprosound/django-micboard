"""Security and write-coalescing regressions for discovery approval."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction

import pytest

from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.discovery_approval_policy import DiscoveryApprovalBatchPolicy
from micboard.services.sync.discovery_approval_resolution import (
    ApprovalIPOwners,
    DiscoveryApprovalResolver,
)
from micboard.services.sync.discovery_approval_service import (
    DiscoveryApprovalResult,
    DiscoveryApprovalService,
)
from tests.factories.base import UserFactory
from tests.factories.discovery import DiscoveryQueueFactory, ManufacturerFactory
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _approve(*items: DiscoveryQueue) -> DiscoveryApprovalResult:
    """Approve only supplied rows as a fully privileged reviewer."""
    return DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk__in=[item.pk for item in items]),
        reviewer=UserFactory(is_staff=True, is_superuser=True),
    )


def _assert_review_pending(item: DiscoveryQueue) -> None:
    """Assert a rejected linked row retained its review state."""
    item.refresh_from_db()
    assert item.status == "pending"
    assert item.reviewed_by is None
    assert item.reviewed_at is None


def test_explicit_chassis_link_cannot_replace_api_identity_without_matching_serial() -> None:
    """An IP-conflict link alone cannot authorize a chassis API-ID takeover."""
    chassis = WirelessChassisFactory(
        api_device_id="established-api-id",
        serial_number="established-serial",
        ip="192.0.2.151",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=chassis.manufacturer,
        existing_device=chassis,
        api_device_id="replacement-api-id",
        serial_number="",
        ip=chassis.ip,
        is_ip_conflict=True,
    )

    with pytest.raises(ValidationError, match="API identity"):
        _approve(queue_item)

    _assert_review_pending(queue_item)
    chassis.refresh_from_db()
    assert queue_item.existing_device_id == chassis.pk
    assert chassis.api_device_id == "established-api-id"
    assert chassis.serial_number == "established-serial"


def test_explicit_chassis_link_cannot_replace_nonblank_serial() -> None:
    """An explicit queue relation cannot override a chassis durable serial."""
    chassis = WirelessChassisFactory(
        api_device_id="serial-protected-api-id",
        serial_number="serial-protected",
        ip="192.0.2.152",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=chassis.manufacturer,
        existing_device=chassis,
        api_device_id=chassis.api_device_id,
        serial_number="replacement-serial",
        ip=chassis.ip,
        is_ip_conflict=True,
    )

    with pytest.raises(ValidationError, match="serial number"):
        _approve(queue_item)

    _assert_review_pending(queue_item)
    chassis.refresh_from_db()
    assert queue_item.existing_device_id == chassis.pk
    assert chassis.serial_number == "serial-protected"


def test_explicit_charger_link_cannot_replace_durable_identity() -> None:
    """A charger IP-conflict relation cannot authorize a serial mismatch."""
    charger = ChargerFactory(
        serial_number="charger-established-serial",
        ip="192.0.2.153",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        existing_charger=charger,
        device_type="charger",
        serial_number="charger-replacement-serial",
        ip=charger.ip,
        is_ip_conflict=True,
    )

    with pytest.raises(ValidationError, match="serial number"):
        _approve(queue_item)

    _assert_review_pending(queue_item)
    charger.refresh_from_db()
    assert queue_item.existing_charger_id == charger.pk
    assert charger.serial_number == "charger-established-serial"


def test_explicit_charger_ip_conflict_requires_nonblank_matching_serial() -> None:
    """A charger IP match without durable identity must remain pending."""
    charger = ChargerFactory(
        serial_number="charger-known-serial",
        ip="192.0.2.154",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        existing_charger=charger,
        device_type="charger",
        serial_number="",
        ip=charger.ip,
        is_ip_conflict=True,
    )

    with pytest.raises(ValidationError, match="lacks a matching charger identity"):
        _approve(queue_item)

    _assert_review_pending(queue_item)
    assert queue_item.existing_charger_id == charger.pk


def test_duplicate_chassis_target_is_saved_once() -> None:
    """Equivalent queue rows must produce one chassis lifecycle execution."""
    first_item = DiscoveryQueueFactory(
        api_device_id="coalesced-api-id",
        serial_number="coalesced-serial",
        ip="192.0.2.155",
        name="First metadata",
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=first_item.manufacturer,
        api_device_id=first_item.api_device_id,
        serial_number=first_item.serial_number,
        ip=first_item.ip,
        name="Last metadata",
    )
    original_save = WirelessChassis.save

    with (
        patch.object(
            WirelessChassis,
            "save",
            autospec=True,
            side_effect=original_save,
        ) as save_chassis,
    ):
        result = _approve(first_item, second_item)

    first_item.refresh_from_db()
    second_item.refresh_from_db()
    save_chassis.assert_called_once()
    assert result.model_dump() == {
        "imported_count": 2,
        "created_count": 1,
        "updated_count": 0,
    }
    assert first_item.existing_device_id == second_item.existing_device_id
    assert first_item.existing_device is not None
    assert first_item.existing_device.name == "Last metadata"


def test_duplicate_charger_target_is_saved_once() -> None:
    """Equivalent charger rows must produce one inventory write."""
    charger = ChargerFactory(ip="192.0.2.156")
    first_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        existing_charger=charger,
        device_type="charger",
        serial_number=charger.serial_number,
        ip=charger.ip,
        name="First charger metadata",
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        existing_charger=charger,
        device_type="charger",
        serial_number=charger.serial_number,
        ip=charger.ip,
        name="Last charger metadata",
    )
    original_save = Charger.save

    with patch.object(
        Charger,
        "save",
        autospec=True,
        side_effect=original_save,
    ) as save_charger:
        result = _approve(first_item, second_item)

    first_item.refresh_from_db()
    second_item.refresh_from_db()
    charger.refresh_from_db()
    save_charger.assert_called_once()
    assert result.model_dump() == {
        "imported_count": 2,
        "created_count": 0,
        "updated_count": 1,
    }
    assert first_item.existing_charger_id == second_item.existing_charger_id == charger.pk
    assert charger.name == "Last charger metadata"


def test_manufacturer_null_charger_rejects_conflicting_batch_manufacturers() -> None:
    """A nullable charger manufacturer cannot become a last-row-wins batch field."""
    charger = ChargerFactory(
        manufacturer=None,
        serial_number="unclaimed-charger-serial",
        ip="192.0.2.157",
    )
    first_item = DiscoveryQueueFactory(
        manufacturer=ManufacturerFactory(),
        existing_charger=charger,
        device_type="charger",
        serial_number=charger.serial_number,
        ip=charger.ip,
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=ManufacturerFactory(),
        existing_charger=charger,
        device_type="charger",
        serial_number=charger.serial_number,
        ip=charger.ip,
    )

    with pytest.raises(ValidationError, match="conflicting manufacturers"):
        _approve(first_item, second_item)

    _assert_review_pending(first_item)
    _assert_review_pending(second_item)
    charger.refresh_from_db()
    assert charger.manufacturer_id is None


def test_owner_snapshot_preserves_duplicate_ids_and_rejects_ambiguity() -> None:
    """Malformed duplicate owners must remain visible to fail-closed policy."""
    ip = "192.0.2.158"
    owner_ids = DiscoveryApprovalResolver._owner_ids_by_ip(
        (
            SimpleNamespace(pk=41, ip=ip),
            SimpleNamespace(pk=42, ip=ip),
        )
    )
    charger = ChargerFactory(ip="192.0.2.159")
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        existing_charger=charger,
        device_type="charger",
        serial_number=charger.serial_number,
        ip=ip,
    )
    policy = DiscoveryApprovalBatchPolicy(
        owners=ApprovalIPOwners(chassis_ids=owner_ids, charger_ids={})
    )

    assert owner_ids == {ip: (41, 42)}
    with pytest.raises(ValidationError, match="multiple wireless chassis"):
        policy.validate_charger(item=queue_item, charger=charger)


def test_inventory_targets_are_prelocked_once_in_stable_model_queries(
    django_assert_num_queries,
) -> None:
    """Cross-IP targets resolve from one pre-locked union without later row locks."""
    first_chassis = WirelessChassisFactory(ip="192.0.2.160")
    second_chassis = WirelessChassisFactory(ip="192.0.2.161")
    first_item = DiscoveryQueueFactory(
        manufacturer=first_chassis.manufacturer,
        existing_device=first_chassis,
        api_device_id=first_chassis.api_device_id,
        serial_number=first_chassis.serial_number,
        ip=second_chassis.ip,
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=second_chassis.manufacturer,
        existing_device=second_chassis,
        api_device_id=second_chassis.api_device_id,
        serial_number=second_chassis.serial_number,
        ip=first_chassis.ip,
    )

    with transaction.atomic():
        inventory = DiscoveryApprovalResolver.lock_inventory([first_item, second_item])
        assert [chassis.pk for chassis in inventory.chassis] == sorted(
            [first_chassis.pk, second_chassis.pk]
        )
        with django_assert_num_queries(0):
            first_target = DiscoveryApprovalResolver.resolve_chassis(
                first_item,
                inventory=inventory,
            )
            second_target = DiscoveryApprovalResolver.resolve_chassis(
                second_item,
                inventory=inventory,
            )

    assert first_target.chassis == first_chassis
    assert second_target.chassis == second_chassis


def test_approval_locks_addresses_before_inventory_rows() -> None:
    """Approval follows the same advisory-lock-before-row-lock order as model saves."""
    item = DiscoveryQueueFactory(ip="192.0.2.162")
    reviewer = UserFactory(is_staff=True, is_superuser=True)
    call_order: list[str] = []
    lock_inventory = DiscoveryApprovalResolver.lock_inventory

    def observe_inventory(items: list[DiscoveryQueue], *, using: str) -> Any:
        call_order.append("inventory")
        return lock_inventory(items, using=using)

    with (
        patch(
            "micboard.services.sync.discovery_approval_service."
            "HardwareIPOwnershipService.lock_addresses",
            side_effect=lambda *args, **kwargs: call_order.append("addresses"),
        ) as lock_addresses,
        patch.object(
            DiscoveryApprovalResolver,
            "lock_inventory",
            side_effect=observe_inventory,
        ),
    ):
        DiscoveryApprovalService().approve(
            queryset=DiscoveryQueue.objects.filter(pk=item.pk),
            reviewer=reviewer,
        )

    assert call_order[:2] == ["addresses", "inventory"]
    locked_values = list(lock_addresses.call_args.args[0])
    assert locked_values == [item.ip]
    assert lock_addresses.call_args.kwargs == {"using": "default"}
