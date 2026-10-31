"""A completed poll takes a chassis the vendor no longer reports offline, once, with one alert."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.alert import Alert
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.chassis_ingest import IngestMode
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.fake_vendor import FakeVendorPlugin, ingest_payloads, use_vendor

pytestmark = pytest.mark.django_db

PRESENT = NormalizedChassis(api_device_id="present", ip="192.0.2.10", serial_number="present-1")


def test_a_chassis_dropped_from_a_complete_snapshot_alerts_although_its_unit_status_is_online(
    watched: SimpleNamespace,
) -> None:
    """The offline alert must fire for a unit whose own status still says online."""
    ingest_payloads(
        [PRESENT],
        manufacturer=watched.manufacturer,
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )

    watched.chassis.refresh_from_db()
    watched.unit.refresh_from_db()
    assert (watched.chassis.status, watched.unit.status) == ("offline", "online")
    alert = Alert.objects.get(user=watched.user)
    assert alert.alert_type == "hardware_offline"


def test_the_alert_and_the_log_carry_last_seen_and_last_online_times(
    watched: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """Operators learn when the chassis was last discoverable from the alert and the log."""
    last_seen = WirelessChassis.objects.get(pk=watched.chassis.pk).last_seen
    last_online_at = WirelessChassis.objects.get(pk=watched.chassis.pk).last_online_at
    assert last_seen is not None and last_online_at is not None

    with caplog.at_level("WARNING", logger="micboard.services.sync.chassis_ingest"):
        ingest_payloads(
            [PRESENT],
            manufacturer=watched.manufacturer,
            mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
        )

    alert = Alert.objects.get(user=watched.user)
    for moment in (last_seen, last_online_at):
        assert moment.isoformat() in alert.message
    assert alert.channel_data["chassis_last_seen"] == last_seen.isoformat()
    assert alert.channel_data["chassis_last_online_at"] == last_online_at.isoformat()
    record = next(r for r in caplog.records if getattr(r, "event.action", "") == "chassis_offline")
    assert getattr(record, "micboard.chassis.last_seen") == last_seen.isoformat()
    assert getattr(record, "micboard.chassis.last_online_at") == last_online_at.isoformat()
    assert last_seen.isoformat() in record.getMessage()
    assert last_online_at.isoformat() in record.getMessage()


def test_a_second_poll_with_the_device_still_missing_changes_nothing_and_alerts_no_more(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace
) -> None:
    """The offline transition and its alert happen exactly once."""
    use_vendor(monkeypatch, FakeVendorPlugin([PRESENT]))

    first = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")
    watched.chassis.refresh_from_db()
    after_first = (watched.chassis.status, watched.chassis.last_offline_at)
    second = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert first.success and second.success
    assert after_first[0] == "offline"
    assert (watched.chassis.status, watched.chassis.last_offline_at) == after_first
    assert Alert.objects.filter(alert_type="hardware_offline").count() == 1


def test_a_complete_poll_takes_the_dropped_chassis_offline(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace
) -> None:
    """The poll itself reconciles, not only a direct snapshot ingest."""
    use_vendor(monkeypatch, FakeVendorPlugin([PRESENT]))

    ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    watched.present.refresh_from_db()
    assert (watched.chassis.status, watched.present.status) == ("offline", "online")
    assert Alert.objects.filter(alert_type="hardware_offline", user=watched.user).count() == 1


def test_a_failed_inventory_fetch_marks_nothing_offline(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace
) -> None:
    """An unreachable vendor API is not an outage of every chassis."""
    plugin = FakeVendorPlugin([PRESENT])
    plugin.get_devices = Mock(side_effect=TimeoutError("vendor unreachable"))  # type: ignore[method-assign]
    use_vendor(monkeypatch, plugin)

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert result.success is False
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


@pytest.mark.parametrize("inventory", [None, []])
def test_an_empty_inventory_marks_nothing_offline(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace, inventory: list[object] | None
) -> None:
    """An empty answer cannot be told from a swallowed bad response, so it never reconciles."""
    plugin = Mock()
    plugin.get_devices.return_value = inventory
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin", Mock(return_value=plugin)
    )

    ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


def test_a_truncated_inventory_marks_nothing_offline(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace, settings: object
) -> None:
    """An inventory larger than the poll limit is incomplete and reconciles nothing."""
    settings.MICBOARD_POLL_MAX_DEVICES = 1  # type: ignore[attr-defined]
    use_vendor(
        monkeypatch,
        FakeVendorPlugin(
            [PRESENT, NormalizedChassis(api_device_id="other", ip="192.0.2.12")],
        ),
    )

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert result.inventory_complete is False
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


@pytest.mark.parametrize(
    "dropped_payload",
    [
        pytest.param(None, id="unnormalizable"),
        pytest.param(NormalizedChassis(api_device_id="dropped"), id="no-address"),
    ],
)
def test_a_poll_that_could_not_read_every_device_marks_nothing_offline(
    monkeypatch: pytest.MonkeyPatch,
    watched: SimpleNamespace,
    dropped_payload: NormalizedChassis | None,
) -> None:
    """A payload skipped before ingest might have named the chassis, so it is not absent."""
    use_vendor(monkeypatch, FakeVendorPlugin([PRESENT, dropped_payload]))

    ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


def test_a_payload_rejected_for_an_identity_conflict_never_counts_as_absent(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace
) -> None:
    """A conflicting payload that still names the chassis keeps it online."""
    conflicting = NormalizedChassis(
        api_device_id="mixed",
        serial_number="dropped-1",
        mac_address=str(watched.present.mac_address or "02:00:00:00:77:01"),
        ip="192.0.2.99",
    )
    WirelessChassis.objects.filter(pk=watched.present.pk).update(mac_address="02:00:00:00:77:01")
    use_vendor(monkeypatch, FakeVendorPlugin([PRESENT, conflicting]))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    watched.chassis.refresh_from_db()
    assert result.devices_rejected == 1
    assert watched.chassis.status == "online"
    assert not Alert.objects.exists()


def test_another_manufacturers_chassis_is_never_taken_offline_by_this_poll(
    monkeypatch: pytest.MonkeyPatch, watched: SimpleNamespace
) -> None:
    """A foreign payload is rejected, and reconciliation never reaches foreign hardware."""
    other = ManufacturerFactory(code="other-vendor")
    foreign_chassis = WirelessChassisFactory(
        manufacturer=other, serial_number="foreign-1", ip="192.0.2.50", status="online"
    )
    foreign = NormalizedChassis(api_device_id="foreign", serial_number="foreign-1", ip="192.0.2.51")
    use_vendor(monkeypatch, FakeVendorPlugin([PRESENT, foreign]))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    foreign_chassis.refresh_from_db()
    assert result.devices_rejected == 1
    assert foreign_chassis.status == "online"


@pytest.mark.parametrize("status", ["retired", "maintenance", "discovered"])
def test_chassis_outside_the_responding_statuses_are_untouched_and_not_alerted(
    watched: SimpleNamespace, status: str
) -> None:
    """Only a chassis that was up can go offline; deliberate states are left alone."""
    WirelessChassis.objects.filter(pk=watched.chassis.pk).update(status=status)

    ingest_payloads(
        [PRESENT],
        manufacturer=watched.manufacturer,
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )

    watched.chassis.refresh_from_db()
    assert watched.chassis.status == status
    assert not Alert.objects.exists()


def test_a_dropped_chassis_without_units_goes_offline_with_its_log_line_and_no_alert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no unit to alert for, the transition and the log line are the whole outcome."""
    manufacturer = ManufacturerFactory(code="unitless-vendor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="online", ip="192.0.2.30")

    with caplog.at_level("WARNING", logger="micboard.services.sync.chassis_ingest"):
        result = ingest_payloads(
            [PRESENT],
            manufacturer=manufacturer,
            mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
        )

    chassis.refresh_from_db()
    assert (chassis.status, result.marked_offline) == ("offline", 1)
    assert any(getattr(r, "event.action", "") == "chassis_offline" for r in caplog.records)
    assert not Alert.objects.exists()


def test_one_alert_budget_covers_every_chassis_a_run_takes_offline() -> None:
    """A large legitimate drop shares one delivery cap instead of one per chassis."""
    manufacturer = ManufacturerFactory(code="budget-vendor")
    for number in range(3):
        WirelessUnitFactory(
            base_chassis=WirelessChassisFactory(
                manufacturer=manufacturer, status="online", ip=f"192.0.2.{40 + number}"
            ),
            manufacturer=manufacturer,
            status="online",
        )

    with patch(
        "micboard.services.sync.chassis_ingest.alert_manager.check_hardware_offline_alerts"
    ) as alerts:
        ingest_payloads(
            [PRESENT],
            manufacturer=manufacturer,
            mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
        )

    assert alerts.call_count == 3
    assert len({id(call.kwargs["budget"]) for call in alerts.call_args_list}) == 1
