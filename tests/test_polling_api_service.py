"""Focused coverage for low-level API polling and discovery dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

from django.test import override_settings

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.api_server_service import APIServerConnectionService
from micboard.services.sync.discovery_trigger_service import trigger_discovery
from micboard.services.sync.polling_api import APIServerPollingService


def _server(**overrides: Any) -> Any:
    """Build the API-server surface consumed by the polling service."""
    values = {
        "pk": 1,
        "name": "Main venue",
        "manufacturer": "shure",
        "status": ManufacturerAPIServer.Status.UNKNOWN,
        "enabled": True,
        "last_health_check": None,
        "status_message": "",
        "base_url": "https://audio.example.test",
        "shared_key": "row-specific-shared-key",
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@patch.object(APIServerPollingService, "poll_server_devices")
@patch.object(ManufacturerAPIServer.objects, "filter")
def test_poll_all_active_devices_isolates_server_failures(
    server_filter: MagicMock,
    poll_server: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One failed API server must not prevent later servers from being polled."""
    servers = [_server(name="one"), _server(name="two"), _server(name="three")]
    server_filter.return_value = servers
    secret = "private-server-shared-key"
    poll_server.side_effect = [None, RuntimeError(f"offline with {secret}"), None]

    result = APIServerPollingService.poll_all_active_devices()

    assert result == {"success": 2, "failed": 1}
    server_filter.assert_called_once_with(enabled=True)
    assert poll_server.call_args_list == [call(server) for server in servers]
    assert secret not in caplog.text


def test_poll_server_devices_ignores_unsupported_manufacturers() -> None:
    """Unsupported manufacturer rows leave server health unchanged."""
    server = _server(manufacturer=ManufacturerAPIServer.Manufacturer.DANTE)

    APIServerPollingService.poll_server_devices(server)

    server.save.assert_not_called()


@patch("micboard.services.sync.polling_api.timezone.now")
@patch("micboard.services.sync.polling_api.HardwareService.sync_hardware_status")
@patch("micboard.services.sync.polling_api.WirelessChassis.objects.filter")
@patch.object(APIServerConnectionService, "fetch_server_devices")
def test_poll_server_devices_updates_known_chassis_and_server_health(
    fetch_devices: MagicMock,
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
    fetch_devices.return_value = [
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
    assert server.status_message == ""
    assert server.last_health_check == timestamp
    server.save.assert_called_once_with(
        update_fields=["status", "status_message", "last_health_check"]
    )


@patch.object(APIServerConnectionService, "fetch_server_devices")
def test_poll_server_devices_records_and_reraises_api_failures(
    fetch_devices: MagicMock,
) -> None:
    """Poll failures persist bounded diagnostics before propagating to the caller."""
    secret = "private-row-shared-key"
    fetch_devices.side_effect = RuntimeError(f"connection failed with {secret}")
    server = _server()

    with pytest.raises(RuntimeError, match="connection failed"):
        APIServerPollingService.poll_server_devices(server)

    assert server.status == ManufacturerAPIServer.Status.ERROR
    assert server.status_message == "Polling failed (RuntimeError)"
    assert secret not in server.status_message
    server.save.assert_called_once_with(update_fields=["status", "status_message"])


@override_settings(MICBOARD_API_SERVER_ALLOWED_HOSTS=["main-a.example.test", "main-b.example.test"])
@patch("micboard.integrations.shure.client.ShureSystemAPIClient")
def test_poll_server_devices_uses_each_rows_connection_and_health(
    client_class: MagicMock,
) -> None:
    """Distinct persisted rows use distinct credentials and record only their own health."""
    timestamp = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    first_context = MagicMock()
    first_context.__enter__.return_value.devices.get_devices.return_value = []
    second_context = MagicMock()
    second_context.__enter__.return_value.devices.get_devices.side_effect = RuntimeError(
        "second server unavailable"
    )
    client_class.side_effect = [first_context, second_context]
    first_server = _server(
        pk=11,
        base_url="https://main-a.example.test:10000",
        shared_key="main-a-row-key",
    )
    second_server = _server(
        pk=12,
        base_url="https://main-b.example.test:10000",
        shared_key="main-b-row-key",
    )

    with patch("micboard.services.sync.polling_api.timezone.now", return_value=timestamp):
        APIServerPollingService.poll_server_devices(first_server)
        with pytest.raises(RuntimeError, match="second server unavailable"):
            APIServerPollingService.poll_server_devices(second_server)

    assert client_class.call_args_list == [
        call(
            base_url="https://main-a.example.test:10000",
            shared_key="main-a-row-key",
        ),
        call(
            base_url="https://main-b.example.test:10000",
            shared_key="main-b-row-key",
        ),
    ]
    first_context.__exit__.assert_called_once()
    second_context.__exit__.assert_called_once()
    assert first_server.status == ManufacturerAPIServer.Status.ACTIVE
    assert first_server.last_health_check == timestamp
    assert second_server.status == ManufacturerAPIServer.Status.ERROR
    assert second_server.last_health_check is None


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
@patch("micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust")
def test_trigger_discovery_rejects_missing_manufacturer_ids(
    send_request: MagicMock,
    _huey_configured: MagicMock,
    manufacturer_id: int | None,
) -> None:
    """Discovery dispatch must never enqueue an unscoped scan."""
    trigger_discovery(manufacturer_id)

    send_request.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=False)
@patch("micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust")
def test_trigger_discovery_skips_dispatch_without_huey(
    send_request: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Unconfigured native Huey is a safe no-op."""
    trigger_discovery(42)

    send_request.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch(
    "micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust",
    return_value=[(object(), None)],
)
def test_trigger_discovery_dispatches_full_scan(
    send_request: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Configured discovery requests both CIDR and FQDN scans."""
    trigger_discovery(42)

    send_request.assert_called_once_with(
        sender=trigger_discovery,
        manufacturer_id=42,
        scan_cidrs=True,
        scan_fqdns=True,
    )
