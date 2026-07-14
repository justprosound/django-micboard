"""Coverage for staged-device refresh service boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

import pytest

from micboard.models.discovery.registry import DiscoveredDevice
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


@patch("micboard.services.sync.device_refresh_service.get_manufacturer_plugin")
def test_refresh_single_applies_transformed_data(get_plugin: MagicMock) -> None:
    discovered = _discovered()
    plugin = get_plugin.return_value.return_value
    plugin.get_device.return_value = {"id": "device-1", "status": "ONLINE"}
    plugin.get_device_channels.return_value = [{"channel": 1}]
    plugin.transform_device_data.return_value = {
        "model": "RX",
        "api_device_id": "updated",
        "channels": "2",
        "status": "online",
    }
    assert DeviceRefreshService()._refresh_single_discovered_device(discovered)
    assert discovered.model == "RX"
    assert discovered.api_device_id == "updated"
    assert discovered.channels == 2
    assert discovered.status == DiscoveredDevice.STATUS_READY
    discovered.save.assert_called_once()


@patch("micboard.services.sync.device_refresh_service.get_manufacturer_plugin")
def test_refresh_single_rejects_missing_inputs_and_transform(get_plugin: MagicMock) -> None:
    service = DeviceRefreshService()
    assert not service._refresh_single_discovered_device(_discovered(manufacturer=None))

    get_plugin.return_value = None
    assert not service._refresh_single_discovered_device(_discovered())

    plugin = Mock(spec=[])
    get_plugin.return_value = Mock(return_value=plugin)
    assert not service._refresh_single_discovered_device(_discovered())


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


def test_channel_enrichment_and_transform_failures_are_contained() -> None:
    service = DeviceRefreshService()
    discovered = _discovered()
    plugin = MagicMock()
    data: dict[str, Any] = {}
    plugin.get_device_channels.return_value = [1]
    service._enrich_device_with_channels(plugin, discovered, data)
    assert data["channels"] == [1]
    plugin.transform_device_data.side_effect = RuntimeError("transform")
    assert service._transform_device(plugin, data, discovered) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ready", DiscoveredDevice.STATUS_READY),
        ("down", DiscoveredDevice.STATUS_OFFLINE),
        ("fault", DiscoveredDevice.STATUS_ERROR),
    ],
)
def test_apply_transformed_maps_status(status: str, expected: str) -> None:
    discovered = _discovered()
    DeviceRefreshService()._apply_transformed_to_discovered(
        discovered,
        {"channels": "invalid", "status": status},
        {"raw": True},
    )
    assert discovered.status == expected
    assert discovered.metadata == {"raw": True}
