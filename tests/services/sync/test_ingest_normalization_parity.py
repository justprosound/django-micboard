"""Ingest normalizes each raw payload once, so poll and realtime differ only in mode."""

import asyncio
from unittest.mock import Mock

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)
from micboard.services.sync.chassis_ingest import ChassisIngestService, IngestMode
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.fake_vendor import FakeVendorPlugin, use_vendor

pytestmark = pytest.mark.django_db(transaction=True)


class CountingVendorPlugin(FakeVendorPlugin):
    """A fake vendor that records how often each raw device was normalized."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.normalized_positions: list[int] = []

    def normalize_device(self, api_data: dict[str, int]):  # type: ignore[no-untyped-def]
        """Count the call, then look the payload up."""
        self.normalized_positions.append(api_data["index"])
        return super().normalize_device(api_data)


def _poll(monkeypatch: pytest.MonkeyPatch, plugin: FakeVendorPlugin) -> None:
    use_vendor(monkeypatch, plugin)
    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")
    assert result is not None


def _realtime(monkeypatch: pytest.MonkeyPatch, plugin: FakeVendorPlugin) -> Mock:
    broadcast = Mock()
    monkeypatch.setattr(BroadcastService, "broadcast_device_update", broadcast)
    plugin.manufacturer = Manufacturer.objects.get(code="vendor")  # type: ignore[attr-defined]
    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin, data=plugin.raw_devices[0], transport="sse"
        )
    )
    return broadcast


@pytest.fixture
def known_chassis() -> WirelessChassis:
    """A chassis the vendor already reported under an API id, serial and address."""
    manufacturer = ManufacturerFactory(code="vendor")
    return WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="known",
        serial_number="known-serial",
        ip="192.0.2.50",
        firmware_version="1.0",
        status="online",
    )


@pytest.mark.parametrize("path", ["poll", "realtime"])
def test_an_event_without_an_address_keeps_the_known_address_on_both_paths(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis, path: str
) -> None:
    """The address backfill is reachable from the poll as well as from realtime."""
    plugin = FakeVendorPlugin([NormalizedChassis(api_device_id="known", firmware_version="2.0")])
    {"poll": _poll, "realtime": _realtime}[path](monkeypatch, plugin)

    known_chassis.refresh_from_db()
    assert (str(known_chassis.ip), known_chassis.firmware_version) == ("192.0.2.50", "2.0")
    assert WirelessChassis.objects.count() == 1


@pytest.mark.parametrize("path", ["poll", "realtime"])
def test_an_event_without_an_address_for_an_unknown_chassis_creates_nothing_on_both_paths(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis, path: str
) -> None:
    """An address-less device nothing names is skipped, never created, on either path."""
    plugin = FakeVendorPlugin([NormalizedChassis(api_device_id="stranger")])
    {"poll": _poll, "realtime": _realtime}[path](monkeypatch, plugin)

    assert list(WirelessChassis.objects.values_list("api_device_id", flat=True)) == ["known"]


def test_a_poll_reports_an_address_less_unknown_device_as_skipped(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis
) -> None:
    """The poll counts the skip the same way whether ingest or the poll saw it first."""
    use_vendor(monkeypatch, FakeVendorPlugin([NormalizedChassis(api_device_id="stranger")]))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    assert (result.devices_skipped, result.devices_examined, result.success) == (1, 1, False)


def test_a_poll_whose_device_cannot_be_identified_leaves_every_chassis_online(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis
) -> None:
    """An address-less unknown device might be the chassis that looks absent."""
    other = WirelessChassisFactory(
        manufacturer=known_chassis.manufacturer, ip="192.0.2.51", status="online"
    )
    use_vendor(monkeypatch, FakeVendorPlugin([NormalizedChassis(api_device_id="stranger")]))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    known_chassis.refresh_from_db()
    other.refresh_from_db()
    assert result.devices_removed == 0
    assert (known_chassis.status, other.status) == ("online", "online")


def test_a_poll_whose_address_less_device_names_a_chassis_still_reconciles_the_rest(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis
) -> None:
    """A backfilled device is identified, so a complete poll can still find the absent chassis."""
    absent = WirelessChassisFactory(
        manufacturer=known_chassis.manufacturer, ip="192.0.2.51", status="online"
    )
    use_vendor(monkeypatch, FakeVendorPlugin([NormalizedChassis(api_device_id="known")]))

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    known_chassis.refresh_from_db()
    absent.refresh_from_db()
    assert result.devices_removed == 1
    assert (known_chassis.status, absent.status) == ("online", "offline")


def test_a_poll_whose_normalizer_raises_counts_the_device_and_marks_nothing_offline(
    monkeypatch: pytest.MonkeyPatch, known_chassis: WirelessChassis
) -> None:
    """A normalizer failure is contained like a realtime one, and blocks reconciliation."""
    plugin = FakeVendorPlugin(
        [NormalizedChassis(api_device_id="other", ip="192.0.2.60"), None, None]
    )
    original = plugin.normalize_device

    def normalize(api_data: dict[str, int]) -> NormalizedChassis | None:
        if api_data["index"] == 1:
            raise ValueError("malformed payload")
        return original(api_data)

    plugin.normalize_device = normalize  # type: ignore[method-assign]
    use_vendor(monkeypatch, plugin)

    result = ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code="vendor")

    known_chassis.refresh_from_db()
    assert result.devices_skipped == 2
    assert result.devices_removed == 0
    assert known_chassis.status == "online"
    assert WirelessChassis.objects.filter(api_device_id="other").exists()


def test_ingest_counts_what_it_could_not_read_and_withholds_reconciliation(
    known_chassis: WirelessChassis,
) -> None:
    """An authoritative snapshot with an unnormalizable or unidentified device reconciles nothing."""
    plugin = FakeVendorPlugin(
        [NormalizedChassis(api_device_id="other", ip="192.0.2.60"), None],
    )
    result = ChassisIngestService.ingest(
        plugin.raw_devices,
        plugin=plugin,
        manufacturer=known_chassis.manufacturer,
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )
    assert (result.created, result.unnormalizable, result.marked_offline) == (1, 1, 0)

    stranger = FakeVendorPlugin([NormalizedChassis(api_device_id="stranger")])
    result = ChassisIngestService.ingest(
        stranger.raw_devices,
        plugin=stranger,
        manufacturer=known_chassis.manufacturer,
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )
    assert (result.skipped, result.unidentified, result.marked_offline) == (1, 1, 0)
    known_chassis.refresh_from_db()
    assert known_chassis.status == "online"


@pytest.mark.parametrize("path", ["poll", "realtime"])
def test_every_raw_payload_is_normalized_exactly_once_on_both_paths(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Neither path normalizes a payload before ingest and again inside it."""
    ManufacturerFactory(code="vendor")
    plugin = CountingVendorPlugin([NormalizedChassis(api_device_id="one", ip="192.0.2.70")])
    {"poll": _poll, "realtime": _realtime}[path](monkeypatch, plugin)

    assert plugin.normalized_positions == [0]
    assert WirelessChassis.objects.filter(api_device_id="one").exists()


def test_a_device_update_normalizes_each_payload_once() -> None:
    """The API-server path shares the same single normalization."""
    manufacturer = ManufacturerFactory(code="vendor")
    plugin = CountingVendorPlugin(
        [
            NormalizedChassis(api_device_id="one", ip="192.0.2.71"),
            NormalizedChassis(api_device_id="two", ip="192.0.2.72"),
        ]
    )

    update = DeviceUpdateService.update_models_from_api_data(
        api_data=plugin.raw_devices, manufacturer=manufacturer, plugin=plugin
    )

    assert plugin.normalized_positions == [0, 1]
    assert update.persisted == 2
    assert update.persisted_api_device_ids == ("one", "two")


def test_a_batch_reports_only_the_ids_it_persisted_when_another_device_is_skipped() -> None:
    """A skipped address-less device is not among the persisted ids a caller broadcasts."""
    manufacturer = ManufacturerFactory(code="vendor")
    plugin = FakeVendorPlugin(
        [
            NormalizedChassis(api_device_id="stranger"),
            NormalizedChassis(api_device_id="two", ip="192.0.2.73"),
        ]
    )

    update = DeviceUpdateService.update_models_from_api_data(
        api_data=plugin.raw_devices, manufacturer=manufacturer, plugin=plugin
    )

    assert (update.persisted, update.skipped) == (1, 1)
    assert update.persisted_api_device_ids == ("two",)


def test_realtime_broadcasts_the_chassis_the_event_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The broadcast carries the persisted chassis, resolved from the ingest result."""
    ManufacturerFactory(code="vendor")
    plugin = FakeVendorPlugin([NormalizedChassis(api_device_id="two", ip="192.0.2.73")])

    broadcast = _realtime(monkeypatch, plugin)

    broadcast.assert_called_once()
    receivers = broadcast.call_args.kwargs["data"]["receivers"]
    assert [receiver["api_device_id"] for receiver in receivers] == ["two"]
