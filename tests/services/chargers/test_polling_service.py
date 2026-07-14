"""Bounded charger polling service contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.test import override_settings

import pytest

from micboard.services.chargers.polling_service import ChargerPollingService


def _manufacturer() -> SimpleNamespace:
    return SimpleNamespace(pk=7, code="shure")


def test_poll_maps_supported_stations_and_checks_health_once() -> None:
    plugin = Mock()
    plugin.get_devices.return_value = [
        {"api_device_id": "station-1", "model": "SBC250"},
        {
            "api_device_id": "station-2",
            "device_type": "MXWNCS4",
            "name": "Green Room Charger",
        },
        {"api_device_id": "receiver-1", "model": "AD4Q"},
        {"api_device_id": 99, "model": "SBC850"},
    ]
    plugin.get_device_channels.side_effect = [
        [
            {
                "channel": 2,
                "tx": {
                    "name": "Handheld 2",
                    "battery_percentage": 87,
                    "charging_status": True,
                },
            },
            {"channel": 3, "tx": None},
        ],
        [],
    ]
    plugin.get_client.return_value.is_healthy.return_value = True

    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set") as cache_set,
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert plugin.get_device_channels.call_args_list == [call("station-1"), call("station-2")]
    plugin.get_client.return_value.is_healthy.assert_called_once_with()
    assert result.scanned_count == 4
    assert result.cached_count == 2
    cache_set.assert_called_once_with(
        "charger_data_shure",
        [
            {
                "id": "station-1",
                "name": "Charger",
                "status": "online",
                "slots": [
                    {
                        "slot_number": 2,
                        "mic_name": "Handheld 2",
                        "battery_level": 87,
                        "charging": True,
                    }
                ],
            },
            {
                "id": "station-2",
                "name": "Green Room Charger",
                "status": "online",
                "slots": [],
            },
        ],
        timeout=60,
    )


@override_settings(
    MICBOARD_CHARGER_MAX_DEVICES=2,
    MICBOARD_CHARGER_MAX_STATIONS=1,
    MICBOARD_CHARGER_MAX_SLOTS=1,
)
def test_poll_bounds_vendor_inventory_stations_and_slots() -> None:
    consumed_devices = 0
    consumed_slots = 0

    def devices():
        nonlocal consumed_devices
        for index in range(4):
            consumed_devices += 1
            yield {"api_device_id": f"station-{index}", "model": "SBC250"}

    def channels(_device_id: str):
        nonlocal consumed_slots
        for index in range(3):
            consumed_slots += 1
            yield {"channel": index, "tx": {"battery_percentage": 150}}

    plugin = Mock()
    plugin.get_devices.side_effect = devices
    plugin.get_device_channels.side_effect = channels
    plugin.get_client.return_value.is_healthy.return_value = True
    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set"),
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert consumed_devices == 3
    assert consumed_slots == 2
    assert result.inventory_truncated is True
    assert result.stations_truncated is True
    assert result.slots_truncated is True
    assert result.cached_count == 1


def test_poll_contains_channel_and_health_secrets_without_publishing_partial_snapshot(
    caplog,
) -> None:
    secret = "credential=private\nforged"
    plugin = Mock()
    plugin.get_devices.return_value = [
        {
            "api_device_id": "station-3",
            "device_type": "SBC220",
            "name": "Wardrobe\nInjected",
        }
    ]
    plugin.get_device_channels.side_effect = RuntimeError(secret)
    plugin.get_client.return_value.is_healthy.side_effect = RuntimeError(secret)

    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set") as cache_set,
        caplog.at_level("ERROR"),
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert secret not in caplog.text
    assert result.failed_count == 1
    assert result.cached_count == 0
    cache_set.assert_not_called()


def test_poll_deduplicates_station_ids_before_channel_requests() -> None:
    plugin = Mock()
    plugin.get_devices.return_value = [
        {"api_device_id": "station-1", "model": "SBC250"},
        {"api_device_id": " station-1 ", "model": "SBC250"},
        {"api_device_id": "station-2", "model": "SBC250"},
    ]
    plugin.get_device_channels.return_value = []
    plugin.get_client.return_value.is_healthy.return_value = True

    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set"),
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert plugin.get_device_channels.call_args_list == [call("station-1"), call("station-2")]
    assert result.scanned_count == 3
    assert result.cached_count == 2


def test_poll_fails_safe_for_invalid_station_ids_and_numeric_fields() -> None:
    plugin = Mock()
    plugin.get_devices.return_value = [
        {"api_device_id": "\n" * 300 + "hidden-id", "model": "SBC250"},
        {"api_device_id": "malformed-model", "model": ["SBC250"]},
        {"api_device_id": "station-1", "model": "SBC250", "name": "\n" * 300 + "hidden"},
    ]
    plugin.get_device_channels.return_value = [
        {"channel": True, "tx": {"battery_percentage": object()}},
        {"channel": object(), "tx": {"battery_percentage": "invalid"}},
    ]
    plugin.get_client.return_value.is_healthy.return_value = True

    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set") as cache_set,
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert result.failed_count == 1
    plugin.get_device_channels.assert_called_once_with("station-1")
    cached = cache_set.call_args.args[1]
    assert cached[0]["name"] == "Charger"
    assert cached[0]["slots"] == [
        {
            "slot_number": 0,
            "mic_name": "Unknown Mic",
            "battery_level": 0,
            "charging": False,
        },
        {
            "slot_number": 0,
            "mic_name": "Unknown Mic",
            "battery_level": 0,
            "charging": False,
        },
    ]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(True, 100), ("invalid", 100), (0, 1), (9999, 500)],
)
def test_device_limit_settings_fail_safe(raw_value: object, expected: int) -> None:
    with override_settings(MICBOARD_CHARGER_MAX_DEVICES=raw_value):
        assert ChargerPollingService.limits().max_devices == expected


def test_non_iterable_inventory_caches_an_empty_snapshot() -> None:
    plugin = Mock()
    plugin.get_devices.return_value = None
    plugin.get_client.return_value.is_healthy.return_value = True
    with (
        patch(
            "micboard.services.chargers.polling_service.get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch("micboard.services.chargers.polling_service.cache.set") as cache_set,
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert result.scanned_count == 0
    assert result.cached_count == 0
    cache_set.assert_called_once_with("charger_data_shure", [], timeout=60)
