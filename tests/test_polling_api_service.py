"""Focused coverage for low-level API polling and discovery dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.sync.discovery_trigger_service import trigger_discovery
from micboard.services.sync.polling_api import APIServerPollingService


def _server(**overrides: Any) -> Any:
    """Build the API-server surface consumed by the polling service."""
    values = {
        "name": "Main venue",
        "manufacturer": "shure",
        "status": ManufacturerAPIServer.Status.UNKNOWN,
        "enabled": True,
        "last_health_check": None,
        "status_message": "",
        "base_url": "https://audio.example.test",
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@patch.object(APIServerPollingService, "poll_server_devices")
@patch.object(ManufacturerAPIServer.objects, "filter")
def test_poll_all_active_devices_isolates_server_failures(
    server_filter: MagicMock,
    poll_server: MagicMock,
) -> None:
    """One failed API server must not prevent later servers from being polled."""
    servers = [_server(name="one"), _server(name="two"), _server(name="three")]
    server_filter.return_value = servers
    poll_server.side_effect = [None, RuntimeError("offline"), None]

    result = APIServerPollingService.poll_all_active_devices()

    assert result == {"success": 2, "failed": 1}
    server_filter.assert_called_once_with(enabled=True)
    assert poll_server.call_args_list == [call(server) for server in servers]


@patch("micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin")
def test_poll_server_devices_ignores_unavailable_plugins(get_plugin: MagicMock) -> None:
    """Missing plugin support leaves server health unchanged."""
    server = _server()
    get_plugin.return_value = None

    APIServerPollingService.poll_server_devices(server)

    server.save.assert_not_called()


@patch(
    "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
    side_effect=LookupError("unsupported"),
)
def test_poll_server_devices_contains_plugin_lookup_errors(get_plugin: MagicMock) -> None:
    """Plugin registry failures are unsupported-server outcomes, not poll failures."""
    server = _server()

    APIServerPollingService.poll_server_devices(server)

    get_plugin.assert_called_once_with("shure")
    server.save.assert_not_called()


@patch("micboard.services.sync.polling_api.timezone.now")
@patch("micboard.services.sync.polling_api.HardwareService.sync_hardware_status")
@patch("micboard.services.sync.polling_api.WirelessChassis.objects.filter")
@patch("micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin")
def test_poll_server_devices_updates_known_chassis_and_server_health(
    get_plugin: MagicMock,
    chassis_filter: MagicMock,
    sync_status: MagicMock,
    now: MagicMock,
) -> None:
    """Valid device payloads update local health while unknown devices are skipped."""
    timestamp = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    now.return_value = timestamp
    online_chassis = SimpleNamespace(last_seen=None, save=Mock())
    offline_chassis = SimpleNamespace(last_seen=None, save=Mock())
    unknown = MagicMock(first=Mock(return_value=None))
    online = MagicMock(first=Mock(return_value=online_chassis))
    offline = MagicMock(first=Mock(return_value=offline_chassis))
    chassis_filter.side_effect = [unknown, online, offline]
    get_plugin.return_value.get_devices.return_value = [
        {"state": "ONLINE"},
        {"serial": "unknown", "state": "ONLINE"},
        {"serialNumber": "online", "state": "ONLINE"},
        {"serial": "offline", "state": "OFFLINE"},
    ]
    server = _server()

    APIServerPollingService.poll_server_devices(server)

    assert chassis_filter.call_args_list == [
        call(serial_number="unknown"),
        call(serial_number="online"),
        call(serial_number="offline"),
    ]
    assert sync_status.call_args_list == [
        call(obj=online_chassis, online=True),
        call(obj=offline_chassis, online=False),
    ]
    assert online_chassis.last_seen == timestamp
    assert offline_chassis.last_seen == timestamp
    online_chassis.save.assert_called_once_with(update_fields=["last_seen"])
    offline_chassis.save.assert_called_once_with(update_fields=["last_seen"])
    assert server.status == ManufacturerAPIServer.Status.ACTIVE
    assert server.last_health_check == timestamp
    server.save.assert_called_once_with(update_fields=["status", "last_health_check"])


@patch("micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin")
def test_poll_server_devices_records_and_reraises_api_failures(get_plugin: MagicMock) -> None:
    """Poll failures persist bounded diagnostics before propagating to the caller."""
    error_message = "connection failed: " + ("x" * 250)
    get_plugin.return_value.get_devices.side_effect = RuntimeError(error_message)
    server = _server()

    with pytest.raises(RuntimeError, match="connection failed"):
        APIServerPollingService.poll_server_devices(server)

    assert server.status == ManufacturerAPIServer.Status.ERROR
    assert server.status_message == error_message[:200]
    server.save.assert_called_once_with(update_fields=["status", "status_message"])


@patch.object(ManufacturerAPIServer.objects, "all")
def test_get_all_server_statuses_aggregates_counts_and_details(all_servers: MagicMock) -> None:
    """Status reporting uses one server collection for totals and serialized details."""
    server = _server(status=ManufacturerAPIServer.Status.ACTIVE)
    queryset = MagicMock()
    queryset.count.return_value = 4
    queryset.filter.side_effect = [
        MagicMock(count=Mock(return_value=3)),
        MagicMock(count=Mock(return_value=2)),
        MagicMock(count=Mock(return_value=1)),
    ]
    queryset.__iter__.return_value = iter([server])
    all_servers.return_value = queryset

    result = APIServerPollingService.get_all_server_statuses()

    assert result == {
        "total": 4,
        "enabled": 3,
        "active": 2,
        "error": 1,
        "servers": [APIServerPollingService.get_server_status(server)],
    }
    assert queryset.filter.call_args_list == [
        call(enabled=True),
        call(status="active"),
        call(status="error"),
    ]


@pytest.mark.parametrize("manufacturer_id", [None, 0])
@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch("micboard.services.sync.discovery_service.DiscoveryService.trigger_manufacturer_discovery")
def test_trigger_discovery_rejects_missing_manufacturer_ids(
    trigger: MagicMock,
    _huey_configured: MagicMock,
    manufacturer_id: int | None,
) -> None:
    """Discovery dispatch must never enqueue an unscoped scan."""
    trigger_discovery(manufacturer_id)

    trigger.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=False)
@patch("micboard.services.sync.discovery_service.DiscoveryService.trigger_manufacturer_discovery")
def test_trigger_discovery_skips_dispatch_without_huey(
    trigger: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Unconfigured native Huey is a safe no-op."""
    trigger_discovery(42)

    trigger.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch("micboard.services.sync.discovery_service.DiscoveryService.trigger_manufacturer_discovery")
def test_trigger_discovery_dispatches_full_scan(
    trigger: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Configured discovery requests both CIDR and FQDN scans."""
    trigger_discovery(42)

    trigger.assert_called_once_with(42, scan_cidrs=True, scan_fqdns=True)
