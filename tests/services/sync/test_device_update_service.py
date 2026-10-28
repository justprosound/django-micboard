"""Focused coverage for polling and realtime device persistence boundaries."""

from unittest.mock import MagicMock, patch

import pytest

from micboard.integrations.sennheiser.normalizer import SENNHEISER_NORMALIZER
from micboard.integrations.shure.normalizer import SHURE_NORMALIZER
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis, NormalizedUnit
from micboard.services.sync.chassis_ingest import IngestMode
from micboard.services.sync.device_update_service import (
    DeviceUpdateResult,
    DeviceUpdateService,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def _plugin(*payloads: NormalizedChassis | Exception | None) -> MagicMock:
    plugin = MagicMock()
    plugin.normalize_device.side_effect = list(payloads)
    plugin.get_device_channels.return_value = []
    plugin.normalize_channels.return_value = []
    return plugin


@pytest.mark.django_db
def test_realtime_update_does_not_reconcile_missing_chassis() -> None:
    """One realtime event cannot mark sibling chassis offline."""
    manufacturer = ManufacturerFactory()
    sibling = WirelessChassisFactory(manufacturer=manufacturer, status="online")

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": "device-1"}],
        manufacturer=manufacturer,
        plugin=_plugin(NormalizedChassis(api_device_id="device-1", ip="192.0.2.31")),
    )

    sibling.refresh_from_db()
    assert updated.persisted == 1
    assert sibling.status == "online"


@pytest.mark.django_db
def test_authoritative_snapshot_reconciles_only_missing_chassis() -> None:
    """Full snapshots mark only the chassis they omit offline."""
    manufacturer = ManufacturerFactory()
    missing = WirelessChassisFactory(manufacturer=manufacturer, status="online")

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": "device-2"}],
        manufacturer=manufacturer,
        plugin=_plugin(NormalizedChassis(api_device_id="device-2", ip="192.0.2.32")),
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )

    missing.refresh_from_db()
    assert updated.persisted == 1
    assert missing.status == "offline"
    assert WirelessChassis.objects.get(api_device_id="device-2").status == "online"


@pytest.mark.django_db
def test_normalization_failure_redacts_raw_device_identifier_and_exception() -> None:
    """A normalization failure cannot disclose raw payload identifiers or exception details."""
    secret = "malformed-payload-secret"
    plugin = _plugin(ValueError(secret))

    with patch("micboard.services.sync.device_update_service.logger") as logger:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "raw-device-3"}],
            manufacturer=ManufacturerFactory(),
            plugin=plugin,
        )

    assert updated.persisted == 0
    assert logger.exception.call_args.args == (
        "Error normalizing vendor device at snapshot position %s",
        1,
    )
    assert "raw-device-3" not in str(logger.exception.call_args)
    assert secret not in str(logger.exception.call_args.kwargs["exc_info"][1])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("normalizer", "device_id"),
    [
        (SHURE_NORMALIZER, "shure-device"),
        (SENNHEISER_NORMALIZER, "sennheiser-device"),
    ],
)
def test_shipped_normalizers_create_online_chassis(normalizer, device_id: str) -> None:
    """Built-in normalized payloads persist responding devices as online."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.side_effect = normalizer.normalize_device
    plugin.get_device_channels.return_value = []
    plugin.normalize_channels.return_value = []

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": device_id, "ip": "192.0.2.81", "modelName": "Receiver"}],
        manufacturer=manufacturer,
        plugin=plugin,
    )

    chassis = WirelessChassis.objects.get(
        manufacturer=manufacturer,
        api_device_id=device_id,
    )
    assert updated.persisted == 1
    assert chassis.status == "online"
    assert chassis.is_online is True


@pytest.mark.django_db
def test_existing_discovered_chassis_reaches_online_through_valid_transitions() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="existing-device",
        ip="192.0.2.82",
        status="discovered",
    )
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id=chassis.api_device_id,
        ip=str(chassis.ip),
    )
    plugin.get_device_channels.return_value = []

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": chassis.api_device_id}],
        manufacturer=manufacturer,
        plugin=plugin,
    )

    chassis.refresh_from_db()
    assert updated.persisted == 1
    assert chassis.status == "online"
    assert chassis.is_online is True


@pytest.mark.django_db
def test_incomplete_authoritative_snapshot_never_marks_devices_offline() -> None:
    """A snapshot with an unnormalizable payload cannot read as an outage."""
    manufacturer = ManufacturerFactory()
    missing = WirelessChassisFactory(manufacturer=manufacturer, status="online")

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": "device-1"}, {"id": "device-2"}],
        manufacturer=manufacturer,
        plugin=_plugin(
            NormalizedChassis(api_device_id="device-1", ip="192.0.2.33"),
            ValueError("malformed payload"),
        ),
        mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
    )

    missing.refresh_from_db()
    assert updated.persisted == 1
    assert missing.status == "online"


@pytest.mark.django_db
def test_unnormalizable_payloads_are_contained() -> None:
    """A payload the integration cannot normalize never reaches chassis persistence."""
    plugin = _plugin(None)

    assert DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": "empty"}],
        manufacturer=ManufacturerFactory(),
        plugin=plugin,
    ) == DeviceUpdateResult(failed=1)


@pytest.mark.django_db
def test_embedded_channels_persist_unit_telemetry_without_a_second_fetch() -> None:
    """Embedded channels are persisted as normalized, and unreported readings use defaults."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="embedded-device",
        ip="192.0.2.91",
        channels=[
            NormalizedChannel(number=1, unit=NormalizedUnit(slot=4)),
            NormalizedChannel(number=2, unit=None),
        ],
    )

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ) as alerts:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "embedded-device"}],
            manufacturer=manufacturer,
            plugin=plugin,
        )

    unit = WirelessUnit.objects.get(base_chassis__api_device_id="embedded-device")
    assert updated.persisted == 1
    assert unit.slot == 4
    assert unit.battery == 255
    assert unit.battery_type == ""
    assert unit.battery_runtime == ""
    assert unit.audio_level == 0
    assert unit.rf_level == 0
    assert unit.tx_offset == 255
    assert unit.quality == 255
    plugin.get_device_channels.assert_not_called()
    plugin.normalize_channels.assert_not_called()
    alerts.assert_called_once_with(unit)


@pytest.mark.django_db
def test_device_without_embedded_channels_uses_the_channel_endpoint() -> None:
    """Snapshots without embedded channels retain the established detail endpoint."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="detail-device",
        ip="192.0.2.92",
    )
    raw_channels = [{"channel": 2}, {"channel": 3, "tx": {"deviceName": "Detail transmitter"}}]
    plugin.get_device_channels.return_value = raw_channels
    plugin.normalize_channels.side_effect = SHURE_NORMALIZER.normalize_channels

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ):
        assert DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "detail-device"}],
            manufacturer=manufacturer,
            plugin=plugin,
        ) == DeviceUpdateResult(persisted=1)

    unit = WirelessUnit.objects.get(base_chassis__api_device_id="detail-device")
    assert unit.assigned_resource.channel_number == 3
    assert unit.name == "Detail transmitter"
    plugin.get_device_channels.assert_called_once_with("detail-device")
    plugin.normalize_channels.assert_called_once_with(raw_channels)


@pytest.mark.django_db
def test_retired_chassis_is_not_revived_by_a_realtime_update() -> None:
    """Realtime persistence never bypasses a rejected lifecycle move."""
    chassis = WirelessChassisFactory(status="retired", api_device_id="retired-device")
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="retired-device",
        ip=str(chassis.ip),
    )
    plugin.get_device_channels.return_value = []
    plugin.normalize_channels.return_value = []

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": "retired-device"}],
        manufacturer=chassis.manufacturer,
        plugin=plugin,
    )

    chassis.refresh_from_db()
    assert (updated.persisted, chassis.status) == (0, "retired")


def test_derived_unit_slot_resolves_collisions_deterministically() -> None:
    """Generated slots advance until they no longer collide with existing units."""
    channel = MagicMock()
    assigned = MagicMock()
    assigned.only.return_value.first.return_value = None
    occupied = MagicMock()
    occupied.exists.side_effect = [True, False]
    with patch.object(WirelessUnit.objects, "filter", side_effect=[assigned, occupied, occupied]):
        slot = DeviceUpdateService._assign_unit_slot(
            channel=channel,
            api_slot=None,
            api_device_id="stable-device",
            channel_number=7,
        )

    assert 0 <= slot < 10000
    assert occupied.exists.call_count == 2
