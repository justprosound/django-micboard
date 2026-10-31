"""The ingest interface owns identity locking, dedup, moves, lifecycle and reconciliation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection

import pytest

from micboard.models.discovery.discovery_queue import DeviceMovementLog
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.sync.chassis_ingest import IngestMode
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.fake_vendor import ingest_payloads

pytestmark = pytest.mark.django_db


def _payload(**overrides: object) -> NormalizedChassis:
    values: dict[str, object] = {
        "api_device_id": "device-1",
        "ip": "192.0.2.100",
        "serial_number": "serial-1",
        "name": "Receiver",
    }
    values.update(overrides)
    return NormalizedChassis(**values)  # type: ignore[arg-type]


def _ingest(
    manufacturer: Manufacturer,
    *payloads: NormalizedChassis,
    mode: IngestMode = IngestMode.PARTIAL_EVENT,
    require_active: bool = True,
):
    return ingest_payloads(
        list(payloads),
        manufacturer=manufacturer,
        mode=mode,
        require_active=require_active,
    )


def test_ingest_locks_before_rebuilding_identity_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DB-backed global lock closes the identity-index/write race window."""
    manufacturer = ManufacturerFactory(code="serialized-vendor")
    events: list[str] = []
    ordered_queryset = Mock()
    ordered_queryset.first.side_effect = lambda: events.append("sentinel-locked") or manufacturer
    lock_queryset = Mock()
    lock_queryset.only.return_value.order_by.return_value = ordered_queryset
    lock_queryset.get.side_effect = lambda **_kwargs: events.append("target-locked") or manufacturer
    select_for_update = Mock(return_value=lock_queryset)
    monkeypatch.setattr(Manufacturer.objects, "select_for_update", select_for_update)
    real_build = DeviceIdentityIndex.build

    def build_index(*args: object, **kwargs: object) -> DeviceIdentityIndex:
        assert connection.in_atomic_block is True
        assert events == ["sentinel-locked", "target-locked"]
        events.append("indexed")
        return real_build(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(DeviceIdentityIndex, "build", build_index)

    result = _ingest(manufacturer, _payload())

    assert result.created == 1
    assert events == ["sentinel-locked", "target-locked", "indexed"]
    assert select_for_update.call_count == 2
    lock_queryset.only.assert_called_once_with("pk")
    lock_queryset.get.assert_called_once_with(pk=manufacturer.pk)


def test_ingest_refuses_to_write_without_a_lock_sentinel() -> None:
    """An absent row is never mistaken for a database-backed serialization lock."""
    with pytest.raises(Manufacturer.DoesNotExist, match="identity mutation lock is unavailable"):
        _ingest(SimpleNamespace(pk=404), _payload())  # type: ignore[arg-type]


def test_a_payload_that_fails_is_counted_and_leaves_no_partial_write() -> None:
    """One failing payload neither blocks its siblings nor leaves half of itself behind."""
    manufacturer = ManufacturerFactory(code="rollback-vendor")
    real_create = WirelessChassisPersistenceService.create_from_normalized

    def create(*, payload: NormalizedChassis, **kwargs: object) -> WirelessChassis:
        chassis = real_create(payload=payload, **kwargs)  # type: ignore[arg-type]
        if payload.api_device_id == "device-2":
            raise RuntimeError("simulated later write failure")
        return chassis

    with patch.object(WirelessChassisPersistenceService, "create_from_normalized", create):
        result = _ingest(
            manufacturer,
            _payload(),
            _payload(api_device_id="device-2", serial_number="serial-2", ip="192.0.2.101"),
        )

    assert (result.created, result.failed) == (1, 1)
    assert list(WirelessChassis.objects.values_list("api_device_id", flat=True)) == ["device-1"]


def test_a_manufacturer_deactivated_before_the_lock_ingests_nothing() -> None:
    """Deactivation during vendor I/O prevents every later inventory mutation."""
    manufacturer = ManufacturerFactory(code="inactive-vendor", is_active=False)

    result = _ingest(manufacturer, _payload())

    assert result.manufacturer_inactive is True
    assert not WirelessChassis.objects.exists()


def test_an_explicit_override_ingests_for_an_inactive_manufacturer() -> None:
    """Only a caller that opts out of the activation check can ingest while inactive."""
    manufacturer = ManufacturerFactory(code="forced-vendor", is_active=False)

    result = _ingest(manufacturer, _payload(), require_active=False)

    assert result.created == 1


def test_a_new_chassis_is_created_in_its_final_online_state() -> None:
    """A responding new device avoids an invalid discovered-to-online follow-up save."""
    manufacturer = ManufacturerFactory(code="new-online-vendor")

    result = _ingest(manufacturer, _payload())

    chassis = result.ingested[0].chassis
    assert result.ingested[0].outcome == "created"
    assert chassis.status == "online"
    assert chassis.is_online is True


def test_a_known_discovered_chassis_reaches_online_through_the_lifecycle() -> None:
    """A duplicate reaches online through both legal lifecycle steps."""
    manufacturer = ManufacturerFactory(code="duplicate-online-vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        ip="192.0.2.100",
        status="discovered",
    )

    result = _ingest(manufacturer, _payload())

    chassis.refresh_from_db()
    assert result.updated == 1
    assert chassis.status == "online"
    assert chassis.last_online_at is not None


def test_a_move_records_the_address_change_once() -> None:
    """A durable identity at a new address writes one movement record."""
    manufacturer = ManufacturerFactory(code="movement-audit-vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        ip="192.0.2.160",
        status="online",
    )

    _ingest(manufacturer, _payload(ip="192.0.2.161"))

    chassis.refresh_from_db()
    movement = DeviceMovementLog.objects.get(device=chassis)
    assert str(chassis.ip) == "192.0.2.161"
    assert (str(movement.old_ip), str(movement.new_ip)) == ("192.0.2.160", "192.0.2.161")
    assert movement.detected_by == "chassis_ingest"


def test_a_move_frees_the_old_address_for_later_payloads_in_the_batch() -> None:
    """A later payload sees a moved chassis at its updated address, not its old one."""
    manufacturer = ManufacturerFactory(code="batch-move-vendor")
    mover = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        ip="192.0.2.140",
    )

    result = _ingest(
        manufacturer,
        _payload(ip="192.0.2.141"),
        _payload(api_device_id="device-2", serial_number="serial-2", ip="192.0.2.140"),
    )

    mover.refresh_from_db()
    assert (result.updated, result.created) == (1, 1)
    assert str(mover.ip) == "192.0.2.141"
    assert WirelessChassis.objects.get(api_device_id="device-2").ip == "192.0.2.140"


def test_an_address_owned_by_another_manufacturer_is_rejected() -> None:
    """An address match never lets one manufacturer update another's chassis."""
    owner = ManufacturerFactory(code="address-owner")
    intruder = ManufacturerFactory(code="address-intruder")
    chassis = WirelessChassisFactory(
        manufacturer=owner,
        serial_number="",
        ip="192.0.2.203",
        name="Protected chassis",
        status="offline",
    )

    result = _ingest(
        intruder,
        _payload(serial_number="", ip="192.0.2.203", name="Attacker-controlled name"),
    )

    chassis.refresh_from_db()
    assert result.ingested == []
    assert (chassis.manufacturer, chassis.name, chassis.status) == (
        owner,
        "Protected chassis",
        "offline",
    )


def test_an_event_without_an_address_keeps_the_known_address() -> None:
    """A partial event naming a known API id updates it without erasing its address."""
    manufacturer = ManufacturerFactory(code="partial-vendor")
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="",
        ip="192.0.2.50",
        firmware_version="1.0",
    )

    result = _ingest(
        manufacturer,
        NormalizedChassis(api_device_id="device-1", firmware_version="2.0"),
    )

    chassis.refresh_from_db()
    assert result.updated == 1
    assert (str(chassis.ip), chassis.firmware_version) == ("192.0.2.50", "2.0")


def test_an_event_without_an_address_for_an_unknown_chassis_creates_nothing() -> None:
    """A chassis cannot be created without an address."""
    manufacturer = ManufacturerFactory(code="addressless-vendor")

    result = _ingest(manufacturer, NormalizedChassis(api_device_id="device-9"))

    assert result.ingested == []
    assert result.failed == 0
    assert not WirelessChassis.objects.exists()


def test_an_authoritative_snapshot_marks_only_absent_chassis_offline() -> None:
    """Chassis missing from a complete snapshot go offline; present ones stay online."""
    manufacturer = ManufacturerFactory(code="snapshot-vendor")
    present = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        ip="192.0.2.100",
        status="online",
    )
    absent = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.101")

    _ingest(manufacturer, _payload(), mode=IngestMode.AUTHORITATIVE_SNAPSHOT)

    present.refresh_from_db()
    absent.refresh_from_db()
    assert (present.status, absent.status) == ("online", "offline")


def test_a_partial_event_never_marks_absent_chassis_offline() -> None:
    """One event says nothing about the chassis it does not mention."""
    manufacturer = ManufacturerFactory(code="event-vendor")
    absent = WirelessChassisFactory(manufacturer=manufacturer, status="online")

    _ingest(manufacturer, _payload(), mode=IngestMode.PARTIAL_EVENT)

    absent.refresh_from_db()
    assert absent.status == "online"


def test_an_incomplete_snapshot_never_marks_chassis_offline() -> None:
    """A snapshot with a failed payload cannot read as an outage."""
    manufacturer = ManufacturerFactory(code="incomplete-vendor")
    absent = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.101")

    with patch.object(
        WirelessChassisPersistenceService, "create_from_normalized", side_effect=RuntimeError("x")
    ):
        result = _ingest(manufacturer, _payload(), mode=IngestMode.AUTHORITATIVE_SNAPSHOT)

    absent.refresh_from_db()
    assert result.failed == 1
    assert absent.status == "online"


def test_ingest_logs_only_database_identifiers() -> None:
    """Ingest logs cannot expose vendor names or device identifiers."""
    private_identity = "private-vendor-device-identity"
    manufacturer = ManufacturerFactory(code=private_identity)

    with patch("micboard.services.sync.chassis_ingest.logger") as logger:
        result = _ingest(manufacturer, _payload(api_device_id=private_identity))

    assert logger.info.call_args.args == (
        "Created wireless chassis %s for manufacturer %s",
        result.ingested[0].chassis.pk,
        manufacturer.pk,
    )
    assert private_identity not in str(logger.method_calls)


def test_snapshot_reconciliation_continues_after_one_lifecycle_failure() -> None:
    """One bad chassis cannot stop sibling offline alerts from being evaluated."""
    manufacturer = ManufacturerFactory(code="reconcile-vendor")
    first = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.61")
    second = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.62")
    unit = WirelessUnitFactory(base_chassis=second, manufacturer=manufacturer, status="online")
    real_mark_offline = HardwareLifecycleManager.mark_offline

    def mark_offline(self: HardwareLifecycleManager, chassis: WirelessChassis, **kwargs: object):
        if chassis.pk == first.pk:
            raise RuntimeError("transition failed")
        return real_mark_offline(self, chassis, **kwargs)  # type: ignore[arg-type]

    with (
        patch.object(HardwareLifecycleManager, "mark_offline", mark_offline),
        patch(
            "micboard.services.sync.chassis_ingest.alert_manager.check_hardware_offline_alerts"
        ) as alerts,
    ):
        _ingest(manufacturer, mode=IngestMode.AUTHORITATIVE_SNAPSHOT)

    second.refresh_from_db()
    assert second.status == "offline"
    alerts.assert_called_once()
    assert alerts.call_args.args == (unit,)


def test_a_move_whose_lifecycle_transition_fails_leaves_the_identity_index_unchanged() -> None:
    """A savepoint rollback must not leave the batch index pointing at the rolled-back address."""
    manufacturer = ManufacturerFactory(code="rollback-vendor")
    WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="device-1",
        serial_number="serial-1",
        ip="192.0.2.180",
        status="online",
    )
    real_bring_online = HardwareLifecycleManager.bring_responding_online
    calls: list[int] = []

    def fail_first(self: HardwareLifecycleManager, chassis: WirelessChassis, **kwargs: object):
        calls.append(chassis.pk)
        if len(calls) == 1:
            raise RuntimeError("transition failed")
        return real_bring_online(self, chassis, **kwargs)  # type: ignore[arg-type]

    with patch.object(HardwareLifecycleManager, "bring_responding_online", fail_first):
        result = _ingest(
            manufacturer,
            _payload(ip="192.0.2.181"),
            _payload(api_device_id="other-id", serial_number="", ip="192.0.2.180"),
        )

    assert result.failed == 1
    assert WirelessChassis.objects.count() == 1
    assert str(WirelessChassis.objects.get().ip) == "192.0.2.180"


def test_a_snapshot_never_marks_offline_a_chassis_a_rejected_payload_still_names() -> None:
    """A conflicting payload still proves the vendor reports its chassis; it is not absent."""
    manufacturer = ManufacturerFactory(code="named-vendor")
    serial_owner = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="serial-owner",
        mac_address="02:00:00:00:40:01",
        ip="192.0.2.140",
        status="online",
    )
    mac_owner = WirelessChassisFactory(
        manufacturer=manufacturer,
        serial_number="mac-owner",
        mac_address="02:00:00:00:40:02",
        ip="192.0.2.141",
        status="online",
    )
    absent = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.142")
    conflicting = _payload(
        api_device_id="mixed",
        serial_number="serial-owner",
        mac_address="02:00:00:00:40:02",
        ip="192.0.2.143",
    )

    result = _ingest(manufacturer, conflicting, mode=IngestMode.AUTHORITATIVE_SNAPSHOT)

    assert (result.rejected, result.skipped, result.failed) == (1, 0, 0)
    for chassis in (serial_owner, mac_owner, absent):
        chassis.refresh_from_db()
    assert (serial_owner.status, mac_owner.status, absent.status) == ("online", "online", "offline")


def test_a_snapshot_never_marks_offline_a_chassis_a_skipped_payload_still_names() -> None:
    """An address-less payload naming a known chassis keeps it out of the absent set."""
    manufacturer = ManufacturerFactory(code="addressless-vendor")
    known = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="known",
        serial_number="known-serial",
        ip="192.0.2.150",
        status="online",
    )
    absent = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.151")

    result = _ingest(
        manufacturer,
        _payload(api_device_id="other", serial_number="known-serial", ip=""),
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )

    known.refresh_from_db()
    absent.refresh_from_db()
    assert (result.skipped, result.rejected) == (1, 0)
    assert (known.status, absent.status) == ("online", "offline")


def test_a_snapshot_alerts_only_for_chassis_it_marked_offline() -> None:
    """A chassis that was already offline does not re-alert on every reconciliation."""
    manufacturer = ManufacturerFactory(code="alert-scope-vendor")
    already_offline = WirelessChassisFactory(
        manufacturer=manufacturer, status="offline", ip="192.0.2.160"
    )
    WirelessUnitFactory(base_chassis=already_offline, manufacturer=manufacturer)
    newly_absent = WirelessChassisFactory(
        manufacturer=manufacturer, status="online", ip="192.0.2.161"
    )
    unit = WirelessUnitFactory(base_chassis=newly_absent, manufacturer=manufacturer)

    with patch(
        "micboard.services.sync.chassis_ingest.alert_manager.check_hardware_offline_alerts"
    ) as alerts:
        _ingest(manufacturer, mode=IngestMode.AUTHORITATIVE_SNAPSHOT)

    alerts.assert_called_once()
    assert alerts.call_args.args == (unit,)


def test_ingest_counts_skipped_and_rejected_payloads() -> None:
    """Every payload that is not persisted is accounted for in the result."""
    manufacturer = ManufacturerFactory(code="counted-vendor")
    other = ManufacturerFactory(code="counted-other")
    WirelessChassisFactory(manufacturer=other, serial_number="foreign", ip="192.0.2.170")

    result = _ingest(
        manufacturer,
        _payload(api_device_id="ok", serial_number="ok", ip="192.0.2.171"),
        _payload(api_device_id="no-address", serial_number="", ip=""),
        _payload(api_device_id="foreign-owned", serial_number="foreign", ip="192.0.2.172"),
    )

    assert (result.created, result.skipped, result.rejected, result.failed) == (1, 1, 1, 0)
