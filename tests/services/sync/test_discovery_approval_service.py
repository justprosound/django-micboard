"""Behavioral coverage for atomic discovery queue approval."""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError

import pytest

from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.discovery_approval_service import DiscoveryApprovalService
from tests.factories.base import UserFactory
from tests.factories.discovery import DiscoveryQueueFactory
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _grant(user, *codenames: str) -> None:
    """Grant Micboard model permissions to a test user."""
    codenames = (*codenames, "change_discoveryqueue")
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="micboard",
            codename__in=codenames,
        )
    )


def test_approval_creates_one_chassis_and_replay_is_idempotent() -> None:
    """A pending queue entry may transition to managed inventory only once."""
    reviewer = UserFactory()
    _grant(reviewer, "add_wirelesschassis")
    queue_item = DiscoveryQueueFactory(
        api_device_id="approval-device",
        serial_number="approval-serial",
        name="Approval Device",
        device_type="receiver",
    )
    queryset = DiscoveryQueue.objects.filter(pk=queue_item.pk)
    service = DiscoveryApprovalService()

    result = service.approve(queryset=queryset, reviewer=reviewer)
    replay_result = service.approve(queryset=queryset, reviewer=reviewer)

    queue_item.refresh_from_db()
    assert result.model_dump() == {
        "imported_count": 1,
        "created_count": 1,
        "updated_count": 0,
    }
    assert replay_result.imported_count == 0
    assert (
        WirelessChassis.objects.filter(
            manufacturer=queue_item.manufacturer,
            api_device_id=queue_item.api_device_id,
        ).count()
        == 1
    )
    assert queue_item.status == "imported"
    assert queue_item.reviewed_by == reviewer
    assert queue_item.reviewed_at is not None


def test_approval_requires_target_inventory_permissions() -> None:
    """Queue review permission cannot grant hardware write access implicitly."""
    reviewer = UserFactory()
    queue_item = DiscoveryQueueFactory(
        api_device_id="forbidden-approval-device",
        serial_number="forbidden-approval-serial",
        device_type="receiver",
    )

    with pytest.raises(PermissionDenied):
        DiscoveryApprovalService().approve(
            queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
            reviewer=reviewer,
        )

    queue_item.refresh_from_db()
    assert queue_item.status == "pending"
    assert not WirelessChassis.objects.filter(
        manufacturer=queue_item.manufacturer,
        api_device_id=queue_item.api_device_id,
    ).exists()


def test_approval_requires_queue_change_permission() -> None:
    """Inventory permission alone cannot authorize a queue workflow transition."""
    reviewer = UserFactory()
    reviewer.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="micboard",
            codename="add_wirelesschassis",
        )
    )
    queue_item = DiscoveryQueueFactory(
        api_device_id="queue-permission-device",
        serial_number="queue-permission-serial",
        device_type="receiver",
    )

    with pytest.raises(PermissionDenied):
        DiscoveryApprovalService().approve(
            queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
            reviewer=reviewer,
        )

    queue_item.refresh_from_db()
    assert queue_item.status == "pending"


def test_approval_updates_a_location_backed_charger() -> None:
    """A discovered charger may update inventory without discarding its location."""
    reviewer = UserFactory()
    _grant(reviewer, "change_charger")
    charger = ChargerFactory(ip="192.0.2.110")
    queue_item = DiscoveryQueueFactory(
        manufacturer=charger.manufacturer,
        serial_number=charger.serial_number,
        ip="192.0.2.111",
        name="Updated Charger",
        device_type="charger",
        existing_charger=charger,
    )

    result = DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
        reviewer=reviewer,
    )

    charger.refresh_from_db()
    queue_item.refresh_from_db()
    assert result.model_dump() == {
        "imported_count": 1,
        "created_count": 0,
        "updated_count": 1,
    }
    assert charger.location_id is not None
    assert charger.ip == "192.0.2.111"
    assert charger.name == "Updated Charger"
    assert queue_item.existing_charger == charger


def test_approval_keeps_unlocated_charger_pending() -> None:
    """A queue record cannot create a charger that violates its location contract."""
    reviewer = UserFactory()
    _grant(reviewer, "change_charger")
    queue_item = DiscoveryQueueFactory(
        serial_number="unlocated-charger",
        name="Unlocated Charger",
        device_type="charger",
    )

    with pytest.raises(ValidationError, match="needs a location"):
        DiscoveryApprovalService().approve(
            queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
            reviewer=reviewer,
        )

    queue_item.refresh_from_db()
    assert queue_item.status == "pending"
    assert queue_item.reviewed_by is None


def test_blank_api_ids_use_distinct_serial_identities() -> None:
    """Serial-only discoveries must not collapse into one blank-API-ID chassis."""
    reviewer = UserFactory()
    _grant(reviewer, "add_wirelesschassis")
    first_item = DiscoveryQueueFactory(
        api_device_id="",
        serial_number="serial-only-one",
        ip="192.0.2.121",
    )
    second_item = DiscoveryQueueFactory(
        manufacturer=first_item.manufacturer,
        api_device_id="",
        serial_number="serial-only-two",
        ip="192.0.2.122",
    )

    result = DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk__in=(first_item.pk, second_item.pk)),
        reviewer=reviewer,
    )

    first_item.refresh_from_db()
    second_item.refresh_from_db()
    assert result.model_dump() == {
        "imported_count": 2,
        "created_count": 2,
        "updated_count": 0,
    }
    assert first_item.existing_device_id != second_item.existing_device_id
    assert {
        first_item.existing_device.api_device_id,
        second_item.existing_device.api_device_id,
    } == {"serial:serial-only-one", "serial:serial-only-two"}


def test_existing_device_identity_change_preserves_known_metadata() -> None:
    """A changed API identity must reuse its linked chassis without blanking metadata."""
    reviewer = UserFactory()
    _grant(reviewer, "change_wirelesschassis")
    chassis = WirelessChassisFactory(
        api_device_id="old-api-id",
        serial_number="known-serial",
        mac_address="00:11:22:33:44:55",
        subnet_mask="255.255.255.0",
        gateway="192.0.2.1",
        name="Known Name",
        fqdn="known.example.test",
        model="Known Model",
        firmware_version="1.2.3",
        ip="192.0.2.123",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=chassis.manufacturer,
        existing_device=chassis,
        api_device_id="new-api-id",
        serial_number=chassis.serial_number,
        name="",
        fqdn="",
        model="",
        firmware_version="",
        metadata={},
        ip=chassis.ip,
    )

    result = DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
        reviewer=reviewer,
    )

    chassis.refresh_from_db()
    queue_item.refresh_from_db()
    assert result.model_dump() == {
        "imported_count": 1,
        "created_count": 0,
        "updated_count": 1,
    }
    assert queue_item.existing_device_id == chassis.pk
    assert WirelessChassis.objects.filter(manufacturer=chassis.manufacturer).count() == 1
    assert chassis.api_device_id == "new-api-id"
    assert chassis.serial_number == "known-serial"
    assert chassis.mac_address == "00:11:22:33:44:55"
    assert chassis.subnet_mask == "255.255.255.0"
    assert chassis.gateway == "192.0.2.1"
    assert chassis.name == "Known Name"
    assert chassis.fqdn == "known.example.test"
    assert chassis.model == "Known Model"
    assert chassis.firmware_version == "1.2.3"


def test_existing_device_preserves_explicit_capacity_before_channel_reconciliation() -> None:
    """An unknown model must not erase a discovered capacity before reconciliation."""
    reviewer = UserFactory()
    _grant(reviewer, "change_wirelesschassis")
    chassis = WirelessChassisFactory(
        model="",
        max_channels=8,
        ip="192.0.2.127",
    )
    assert chassis.rf_channels.count() == 8
    queue_item = DiscoveryQueueFactory(
        manufacturer=chassis.manufacturer,
        existing_device=chassis,
        api_device_id=chassis.api_device_id,
        serial_number=chassis.serial_number,
        model="UNRECOGNIZED-MODEL",
        ip=chassis.ip,
    )

    DiscoveryApprovalService().approve(
        queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
        reviewer=reviewer,
    )

    chassis.refresh_from_db()
    assert chassis.max_channels == 8
    assert chassis.rf_channels.count() == chassis.max_channels


def test_ambiguous_charger_fallback_leaves_queue_pending() -> None:
    """Manufacturer and serial fallback must reject ambiguous charger inventory."""
    reviewer = UserFactory()
    _grant(reviewer, "change_charger")
    first_charger = ChargerFactory(
        serial_number="ambiguous-serial",
        ip="192.0.2.124",
    )
    ChargerFactory(
        manufacturer=first_charger.manufacturer,
        serial_number=first_charger.serial_number,
        ip="192.0.2.125",
    )
    queue_item = DiscoveryQueueFactory(
        manufacturer=first_charger.manufacturer,
        serial_number=first_charger.serial_number,
        ip="192.0.2.126",
        device_type="charger",
        existing_charger=None,
    )

    with pytest.raises(ValidationError, match="matches multiple inventory records"):
        DiscoveryApprovalService().approve(
            queryset=DiscoveryQueue.objects.filter(pk=queue_item.pk),
            reviewer=reviewer,
        )

    queue_item.refresh_from_db()
    assert queue_item.status == "pending"
    assert queue_item.reviewed_by is None
    assert queue_item.reviewed_at is None
    assert queue_item.existing_charger is None
