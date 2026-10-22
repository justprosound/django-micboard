"""Coverage for staged-device refresh service boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

import pytest

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis
from micboard.services.sync.device_refresh_service import DeviceRefreshService


def _manufacturer(code: str = "test") -> Any:
    return SimpleNamespace(code=code, name=code.title())


def _discovered(**overrides: Any) -> Any:
    values = {
        "pk": 1,
        "manufacturer": _manufacturer(),
        "ip": "192.0.2.1",
        "api_device_id": "device-1",
        "metadata": {},
        "model": "",
        "channels": 0,
        "status": DiscoveredDevice.STATUS_PENDING,
        "STATUS_READY": DiscoveredDevice.STATUS_READY,
        "STATUS_OFFLINE": DiscoveredDevice.STATUS_OFFLINE,
        "STATUS_ERROR": DiscoveredDevice.STATUS_ERROR,
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_refresh_many_counts_success_and_failure() -> None:
    service = cast(Any, DeviceRefreshService())
    service._refresh_single_discovered_device = Mock(side_effect=[True, False, True])
    assert service.refresh_discovered_devices_from_api([1, 2, 3]) == (2, 1)


@patch("micboard.services.sync.device_refresh_service.build_manufacturer_plugin")
def test_refresh_single_applies_normalized_device(get_plugin: MagicMock) -> None:
    discovered = _discovered()
    plugin = get_plugin.return_value
    plugin.get_device.return_value = {"id": "device-1"}
    plugin.get_device_channels.return_value = [{"channel": 1}, {"channel": 2}]
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="updated",
        model="RX",
        channels=[NormalizedChannel(number=1), NormalizedChannel(number=2)],
    )
    assert DeviceRefreshService()._refresh_single_discovered_device(discovered)
    assert discovered.model == "RX"
    assert discovered.api_device_id == "updated"
    assert discovered.channels == 2
    assert discovered.status == DiscoveredDevice.STATUS_PENDING
    plugin.normalize_device.assert_called_once_with(
        {"id": "device-1", "channels": [{"channel": 1}, {"channel": 2}]}
    )
    discovered.save.assert_called_once()


@patch("micboard.services.sync.device_refresh_service.build_manufacturer_plugin")
def test_refresh_single_contains_plugin_loading_failure(get_plugin: MagicMock) -> None:
    discovered = _discovered()
    get_plugin.side_effect = ModuleNotFoundError("integration unavailable")

    assert not DeviceRefreshService()._refresh_single_discovered_device(discovered)
    discovered.save.assert_not_called()


def test_refresh_single_rejects_device_without_manufacturer() -> None:
    discovered = _discovered(manufacturer=None)

    assert not DeviceRefreshService()._refresh_single_discovered_device(discovered)
    discovered.save.assert_not_called()


@patch("micboard.services.sync.device_refresh_service.build_manufacturer_plugin")
def test_refresh_single_returns_false_without_device_data(get_plugin: MagicMock) -> None:
    discovered = _discovered()
    plugin = get_plugin.return_value
    plugin.get_device.return_value = None
    plugin.get_devices.return_value = []

    assert not DeviceRefreshService()._refresh_single_discovered_device(discovered)
    discovered.save.assert_not_called()


@patch("micboard.services.sync.device_refresh_service.build_manufacturer_plugin")
def test_refresh_single_preserves_raw_data_when_normalization_returns_none(
    get_plugin: MagicMock,
) -> None:
    discovered = _discovered()
    plugin = get_plugin.return_value
    plugin.get_device.return_value = {"raw": True}
    plugin.get_device_channels.return_value = []
    plugin.normalize_device.return_value = None

    assert not DeviceRefreshService()._refresh_single_discovered_device(discovered)
    assert discovered.metadata == {"raw": True, "channels": []}
    discovered.save.assert_called_once()


def test_device_data_lookup_falls_back_to_device_list() -> None:
    service = DeviceRefreshService()
    discovered = _discovered()
    plugin = MagicMock()
    plugin.get_device.side_effect = RuntimeError("detail")
    plugin.get_devices.return_value = [
        {"ip": "198.51.100.1"},
        {"ipAddress": "192.0.2.1", "id": "match"},
    ]
    device_data = service._get_device_data_from_plugin(plugin, discovered)
    assert device_data is not None
    assert device_data["id"] == "match"
    plugin.get_devices.side_effect = RuntimeError("list")
    assert service._get_device_data_from_plugin(plugin, discovered) is None


@pytest.mark.parametrize("address_key", ["ip", "ipAddress"])
def test_device_data_list_lookup_matches_supported_address_keys(address_key: str) -> None:
    service = DeviceRefreshService()
    discovered = _discovered(api_device_id="")
    plugin = MagicMock()
    plugin.get_devices.return_value = [{address_key: discovered.ip, "id": "match"}]

    assert service._get_device_data_from_plugin(plugin, discovered) == {
        address_key: discovered.ip,
        "id": "match",
    }
    plugin.get_device.assert_not_called()


def test_channel_enrichment_and_normalization_failures_are_contained() -> None:
    service = DeviceRefreshService()
    discovered = _discovered()
    plugin = MagicMock()
    data: dict[str, Any] = {}
    plugin.get_device_channels.return_value = [1]
    service._enrich_device_with_channels(plugin, discovered, data)
    assert data["channels"] == [1]
    plugin.normalize_device.side_effect = RuntimeError("normalize")
    assert service._normalize_device(plugin, data, discovered) is None

    plugin.get_device_channels.side_effect = RuntimeError("channels")
    service._enrich_device_with_channels(plugin, discovered, data)
    service._enrich_device_with_channels(plugin, _discovered(api_device_id=""), data)


def test_apply_normalized_keeps_existing_values_the_device_did_not_report() -> None:
    """An empty model or channel list preserves what the staged record already knew."""
    discovered = _discovered(model="Existing", api_device_id="existing", channels=4)

    DeviceRefreshService()._apply_normalized_to_discovered(
        discovered,
        NormalizedChassis(api_device_id="existing"),
        {"raw": True},
    )

    assert discovered.model == "Existing"
    assert discovered.channels == 4
    assert discovered.metadata == {"raw": True}
    assert discovered.status == DiscoveredDevice.STATUS_PENDING
