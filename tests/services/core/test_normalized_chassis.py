"""One normalized chassis shape, read the same way by every persistence path."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from micboard.integrations.sennheiser.normalizer import SENNHEISER_NORMALIZER
from micboard.integrations.shure.normalizer import SHURE_NORMALIZER
from micboard.models.discovery.discovery_queue import DeviceMovementLog
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis, NormalizedUnit
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.device_promotion_service import DevicePromotionService
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import DiscoveredDeviceFactory, ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def _shure_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "shure-rx-1",
        "ipAddress": "192.0.2.10",
        "type": "ULXD",
        "modelName": "ULXD4Q",
        "serialNumber": "SN-0001",
        "macAddress": "00-11-22-33-44-55",
        "firmwareVersion": "2.7.1",
        "channels": [
            {"channel": 1, "tx": {"batteryBars": 4, "deviceName": "Lectern"}},
            {"channel": 2},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("normalizer", [SHURE_NORMALIZER, SENNHEISER_NORMALIZER])
def test_normalizers_keep_vendor_identity(normalizer) -> None:
    """The full model, serial, and MAC reach the normalized chassis under one name each."""
    chassis = normalizer.normalize_device(_shure_payload())

    assert isinstance(chassis, NormalizedChassis)
    assert chassis.api_device_id == "shure-rx-1"
    assert chassis.ip == "192.0.2.10"
    assert chassis.model == "ULXD4Q"
    assert chassis.serial_number == "SN-0001"
    assert chassis.mac_address == "00:11:22:33:44:55"
    assert chassis.firmware_version == "2.7.1"
    assert [channel.number for channel in chassis.channels] == [1, 2]
    assert chassis.channels[0].unit is not None
    assert chassis.channels[0].unit.battery == 4
    assert chassis.channels[0].unit.name == "Lectern"
    assert chassis.channels[1].unit is None


def test_normalizer_derives_role_from_the_device_specification() -> None:
    """A model the specification lists as a transmitter is not persisted as a receiver."""
    chassis = SHURE_NORMALIZER.normalize_device(_shure_payload(modelName="ADPSM", type="AD"))

    assert chassis is not None
    assert chassis.role == "transmitter"


def test_normalizer_never_invents_a_model_number() -> None:
    """A payload without a model name leaves the model empty rather than guessing one."""
    payload = _shure_payload()
    del payload["modelName"]

    chassis = SHURE_NORMALIZER.normalize_device(payload)

    assert chassis is not None
    assert chassis.model == ""
    assert chassis.role is None


@pytest.mark.parametrize("payload", [{}, {"id": "  "}, {"id": "rx", "channels": "not-a-list"}])
def test_normalizer_rejects_unusable_payloads(payload: dict[str, object]) -> None:
    """A payload without an identifier or with a malformed shape yields no chassis."""
    assert SHURE_NORMALIZER.normalize_device(payload) is None


def test_normalizer_maps_unit_telemetry_and_keeps_channels_without_units() -> None:
    """Every telemetry field lands under one name, and empty channels stay visible."""
    chassis = SHURE_NORMALIZER.normalize_device(
        {
            "id": "receiver-1",
            "channels": [
                {
                    "channelNumber": 2,
                    "transmitter": {
                        "batteryBars": 4,
                        "batteryCharge": 90,
                        "batteryRuntimeMinutes": 125,
                        "batteryHealth": "good",
                        "batteryCycles": 12,
                        "batteryTemperatureC": 28,
                        "audioLevel": -10,
                        "rfLevel": 70,
                        "frequency": 550.1,
                        "antenna": 1,
                        "status": "online",
                        "audioQuality": 99,
                        "txOffset": 2,
                        "deviceName": "Lead",
                        "batteryType": "lithium",
                    },
                },
                {"channel": 3, "tx": {}},
            ],
        }
    )

    assert chassis is not None
    assert chassis.channels[0] == NormalizedChannel(
        number=2,
        unit=NormalizedUnit(
            slot=2,
            battery=4,
            battery_charge=90,
            battery_type="lithium",
            runtime="02:05",
            battery_health="good",
            battery_cycles=12,
            battery_temperature_c=28.0,
            audio_level=-10,
            rf_level=70,
            frequency="550.1",
            antenna="1",
            tx_offset=2,
            quality=99,
            status="online",
            name="Lead",
        ),
    )
    assert chassis.channels[1] == NormalizedChannel(number=3, unit=None)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(None, ""), (-1, ""), (61, "01:01"), (float("nan"), ""), ("soon", "")],
)
def test_normalizer_formats_runtime_or_leaves_it_empty(minutes: object, expected: str) -> None:
    """A runtime the device cannot express in whole minutes is left empty."""
    chassis = SHURE_NORMALIZER.normalize_device(
        {"id": "rx", "channels": [{"channel": 1, "tx": {"batteryRuntimeMinutes": minutes}}]}
    )

    assert chassis is not None
    assert chassis.channels[0].unit is not None
    assert chassis.channels[0].unit.runtime == expected


def test_normalizer_drops_an_unusable_unit_but_keeps_its_channel() -> None:
    """One malformed reading costs that unit, not the whole chassis."""
    chassis = SHURE_NORMALIZER.normalize_device(
        {"id": "rx", "channels": [{"channel": 1, "tx": {"batteryBars": "full"}}]}
    )

    assert chassis is not None
    assert chassis.channels == [NormalizedChannel(number=1, unit=None)]


class _BrokenMapping(dict):
    """Payload double whose every read fails."""

    def get(self, *_args, **_kwargs):
        raise RuntimeError("broken payload")


def test_normalizer_contains_a_payload_that_cannot_be_read() -> None:
    """A payload that raises on access yields no chassis instead of escaping."""
    assert SHURE_NORMALIZER.normalize_device(_BrokenMapping()) is None


@pytest.mark.parametrize(
    ("normalizer", "raw_type", "expected"),
    [
        (SHURE_NORMALIZER, "Axient Digital", "Axient Digital"),
        (SHURE_NORMALIZER, "P10T", "P10T"),
        (SHURE_NORMALIZER, "unsupported", "Unknown"),
        (SENNHEISER_NORMALIZER, "EW-D", "Evolution Wireless Digital"),
        (SENNHEISER_NORMALIZER, "Team Connect", "TeamConnect"),
        (SENNHEISER_NORMALIZER, "", "Unknown"),
    ],
)
def test_normalizers_name_unnamed_devices_after_their_family(
    normalizer, raw_type: str, expected: str
) -> None:
    """Each integration names its own device families."""
    chassis = normalizer.normalize_device({"id": "rx", "type": raw_type})

    assert chassis is not None
    assert chassis.name == expected
    assert chassis.model == ""


def test_normalizer_canonicalizes_mac_identity_only() -> None:
    """Vendor MAC spelling does not change identity, and names are not read as MACs."""
    chassis = SHURE_NORMALIZER.normalize_device(
        {"id": " rx ", "macAddress": "AABBCCDDEEFF", "name": " AA-BB is a name "}
    )

    assert chassis is not None
    assert chassis.api_device_id == "rx"
    assert chassis.mac_address == "aa:bb:cc:dd:ee:ff"
    assert chassis.name == "AA-BB is a name"


@pytest.mark.django_db
def test_poll_and_realtime_persist_the_same_model() -> None:
    """A chassis keeps its full model whichever path last wrote it."""
    manufacturer = ManufacturerFactory(code="shure-normalized")
    plugin = Mock()
    plugin.get_devices.return_value = [_shure_payload()]
    plugin.normalize_device.side_effect = SHURE_NORMALIZER.normalize_device
    plugin.normalize_channels.side_effect = SHURE_NORMALIZER.normalize_channels

    with patch(
        "micboard.services.manufacturer.sync.build_manufacturer_plugin",
        return_value=plugin,
    ):
        result = ManufacturerSyncService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer.code,
        )
    assert result.devices_added == 1
    chassis = WirelessChassis.objects.get(manufacturer=manufacturer, api_device_id="shure-rx-1")
    assert chassis.model == "ULXD4Q"
    assert chassis.serial_number == "SN-0001"
    assert chassis.role == "receiver"

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ):
        DeviceUpdateService.update_models_from_api_data(
            api_data=[_shure_payload()],
            manufacturer=manufacturer,
            plugin=plugin,
        )

    chassis.refresh_from_db()
    assert chassis.model == "ULXD4Q"

    event = {"id": "shure-rx-1", "ipAddress": "192.0.2.10", "type": "ULXD"}
    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ):
        DeviceUpdateService.update_models_from_api_data(
            api_data=[event],
            manufacturer=manufacturer,
            plugin=plugin,
        )

    chassis.refresh_from_db()
    assert chassis.model == "ULXD4Q"


@pytest.mark.django_db
def test_promotion_deduplicates_by_vendor_serial() -> None:
    """Promotion updates the chassis that already owns the serial instead of creating one."""
    manufacturer = ManufacturerFactory(code="shure-promotion")
    existing = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="old-api-id",
        serial_number="SN-0001",
        mac_address=None,
        ip="192.0.2.99",
    )
    discovered = DiscoveredDeviceFactory(manufacturer=manufacturer, ip="192.0.2.10")
    plugin = Mock()
    plugin.normalize_device.side_effect = SHURE_NORMALIZER.normalize_device

    success, _message, chassis = DevicePromotionService()._attempt_promotion_with_device_data(
        discovered,
        plugin,
        _shure_payload(macAddress=None),
    )

    assert success is True
    assert chassis is not None
    assert chassis.pk == existing.pk
    assert WirelessChassis.objects.filter(manufacturer=manufacturer).count() == 1
    existing.refresh_from_db()
    assert existing.ip == "192.0.2.10"
    assert existing.model == "ULXD4Q"
    assert DeviceMovementLog.objects.filter(
        device=existing,
        old_ip="192.0.2.99",
        new_ip="192.0.2.10",
    ).exists()
