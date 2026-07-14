"""Service-level coverage for discovery orchestration and persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.sync.discovery_orchestration_service import DiscoveryOrchestrationService
from tests.factories.discovery import ManufacturerFactory

pytestmark = pytest.mark.django_db


def test_discovery_request_syncs_devices_and_broadcasts_scope() -> None:
    manufacturer = ManufacturerFactory(code="shure")
    devices = [{"ip": "192.0.2.60"}, {"ip": "192.0.2.61"}]
    plugin = MagicMock()
    plugin.get_devices.return_value = devices
    plugin_class = MagicMock(return_value=plugin)

    with (
        patch(
            "micboard.services.common.base.plugin.get_manufacturer_plugin",
            return_value=plugin_class,
        ),
        patch(
            "micboard.services.sync.hardware_sync_service.HardwareSyncService.bulk_sync_devices",
            return_value={"added": 1, "updated": 1},
        ) as bulk_sync,
        patch(
            "micboard.services.notification.broadcast_service."
            "BroadcastService.broadcast_device_update"
        ) as broadcast,
    ):
        result = DiscoveryOrchestrationService.handle_discovery_requested(
            manufacturer_code="shure",
            organization_id=7,
            campus_id=9,
        )

    assert result == {
        "shure": {
            "status": "success",
            "device_count": 2,
            "updated": 1,
            "added": 1,
        }
    }
    plugin_class.assert_called_once_with(manufacturer)
    bulk_sync.assert_called_once_with(
        manufacturer=manufacturer,
        devices_data=devices,
        organization_id=7,
    )
    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        data={"device_count": 2},
        organization_id=7,
        campus_id=9,
    )


def test_discovery_request_treats_missing_plugin_devices_as_empty() -> None:
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.get_devices.return_value = None

    with (
        patch(
            "micboard.services.common.base.plugin.get_manufacturer_plugin",
            return_value=MagicMock(return_value=plugin),
        ),
        patch(
            "micboard.services.sync.hardware_sync_service.HardwareSyncService.bulk_sync_devices",
            return_value={"added": 0, "updated": 0},
        ) as bulk_sync,
        patch(
            "micboard.services.notification.broadcast_service."
            "BroadcastService.broadcast_device_update"
        ),
    ):
        result = DiscoveryOrchestrationService.handle_discovery_requested()

    assert result[manufacturer.code]["device_count"] == 0
    assert bulk_sync.call_args.kwargs["devices_data"] == []


def test_discovery_request_isolates_manufacturer_failure() -> None:
    failing = ManufacturerFactory(code="failing")
    healthy = ManufacturerFactory(code="healthy")
    failing_plugin = MagicMock()
    failing_plugin.get_devices.side_effect = RuntimeError("vendor failed")
    healthy_plugin = MagicMock()
    healthy_plugin.get_devices.return_value = []

    def plugin_for(code: str) -> MagicMock:
        plugin = failing_plugin if code == failing.code else healthy_plugin
        return MagicMock(return_value=plugin)

    with (
        patch(
            "micboard.services.common.base.plugin.get_manufacturer_plugin",
            side_effect=plugin_for,
        ),
        patch(
            "micboard.services.sync.hardware_sync_service.HardwareSyncService.bulk_sync_devices",
            return_value={"added": 0, "updated": 0},
        ),
        patch(
            "micboard.services.notification.broadcast_service."
            "BroadcastService.broadcast_device_update"
        ),
    ):
        result = DiscoveryOrchestrationService.handle_discovery_requested()

    assert result[failing.code] == {"status": "error", "error": "vendor failed"}
    assert result[healthy.code]["status"] == "success"


def test_device_detail_requires_device_id() -> None:
    assert DiscoveryOrchestrationService.handle_device_detail_requested() == {
        "status": "error",
        "error": "device_id required",
    }


@pytest.mark.parametrize("channels_fail", [False, True])
def test_device_detail_returns_first_vendor_match(channels_fail: bool) -> None:
    manufacturer = ManufacturerFactory(code="detail")
    plugin = MagicMock()
    plugin.get_device.return_value = {"id": "device-1", "model": "RX"}
    if channels_fail:
        plugin.get_device_channels.side_effect = RuntimeError("channels unavailable")
    else:
        plugin.get_device_channels.return_value = [{"index": 1}]

    with patch(
        "micboard.services.common.base.plugin.get_manufacturer_plugin",
        return_value=MagicMock(return_value=plugin),
    ):
        result = DiscoveryOrchestrationService.handle_device_detail_requested(
            manufacturer_code=manufacturer.code,
            device_id="device-1",
        )

    device = result[manufacturer.code]["device"]
    assert device["id"] == "device-1"
    if channels_fail:
        assert "channels" not in device
    else:
        assert device["channels"] == [{"index": 1}]


def test_device_detail_reports_not_found_after_all_vendors() -> None:
    ManufacturerFactory()
    plugin = MagicMock()
    plugin.get_device.return_value = None

    with patch(
        "micboard.services.common.base.plugin.get_manufacturer_plugin",
        return_value=MagicMock(return_value=plugin),
    ):
        result = DiscoveryOrchestrationService.handle_device_detail_requested(device_id="missing")

    assert result == {"status": "error", "error": "device not found"}


def test_device_detail_reports_vendor_failure() -> None:
    manufacturer = ManufacturerFactory(code="broken")

    with patch(
        "micboard.services.common.base.plugin.get_manufacturer_plugin",
        side_effect=RuntimeError("plugin unavailable"),
    ):
        result = DiscoveryOrchestrationService.handle_device_detail_requested(
            manufacturer_code=manufacturer.code,
            device_id="device-1",
        )

    assert result == {"broken": {"status": "error", "error": "plugin unavailable"}}


def test_persist_discovered_devices_normalizes_vendor_payloads() -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    DiscoveryOrchestrationService._persist_discovered_devices(
        [
            {
                "communicationProtocol": {"address": "192.0.2.70"},
                "type": "receiver",
                "channels": [{"index": 1}, {"index": 2}],
                "hardwareIdentity": {"deviceId": "shure-1"},
                "softwareIdentity": {"model": "AD4Q"},
                "compatibility": "COMPATIBLE",
                "deviceState": "ONLINE",
            },
            {
                "ipAddress": "192.0.2.71",
                "deviceType": "transmitter",
                "deviceModel": "Generic TX",
                "deviceId": "generic-1",
                "status": "offline",
                "firmware": "1.2.3",
            },
            {"id": "missing-address"},
        ],
        manufacturer,
    )

    shure = DiscoveredDevice.objects.get(ip="192.0.2.70")
    generic = DiscoveredDevice.objects.get(ip="192.0.2.71")
    assert (shure.model, shure.api_device_id, shure.channels, shure.status) == (
        "AD4Q",
        "shure-1",
        2,
        DiscoveredDevice.STATUS_READY,
    )
    assert (generic.model, generic.api_device_id, generic.status) == (
        "Generic TX",
        "generic-1",
        DiscoveredDevice.STATUS_OFFLINE,
    )
    assert generic.metadata == {
        "deviceType": "transmitter",
        "status": "offline",
        "firmware": "1.2.3",
    }
    assert DiscoveredDevice.objects.count() == 2


def test_persist_discovered_devices_updates_existing_vendor_record() -> None:
    manufacturer = ManufacturerFactory()
    DiscoveredDevice.objects.create(
        ip="192.0.2.72",
        manufacturer=manufacturer,
        device_type="unknown",
    )

    DiscoveryOrchestrationService._persist_discovered_devices(
        [
            {
                "ip": "192.0.2.72",
                "type": "receiver",
                "model": "Updated Model",
                "id": "updated-id",
                "status": "active",
            }
        ],
        manufacturer,
    )

    discovered = DiscoveredDevice.objects.get(ip="192.0.2.72")
    assert discovered.device_type == "receiver"
    assert discovered.model == "Updated Model"
    assert discovered.api_device_id == "updated-id"
    assert discovered.status == DiscoveredDevice.STATUS_READY


@pytest.mark.parametrize(
    ("state", "compatibility", "expected_status"),
    [
        ("DISCOVERED", "COMPATIBLE", DiscoveredDevice.STATUS_PENDING),
        ("ERROR", "COMPATIBLE", DiscoveredDevice.STATUS_ERROR),
        ("OFFLINE", "COMPATIBLE", DiscoveredDevice.STATUS_OFFLINE),
        ("UNKNOWN", "COMPATIBLE", DiscoveredDevice.STATUS_UNKNOWN),
        ("ONLINE", "INCOMPATIBLE_TOO_NEW", DiscoveredDevice.STATUS_INCOMPATIBLE),
    ],
)
def test_shure_status_normalization(
    state: str,
    compatibility: str,
    expected_status: str,
) -> None:
    _, _, _, status = DiscoveryOrchestrationService._extract_shure_fields(
        {"deviceState": state, "compatibility": compatibility}
    )

    assert status == expected_status


@pytest.mark.parametrize(
    ("status", "expected_status"),
    [
        ("ready", DiscoveredDevice.STATUS_READY),
        ("inactive", DiscoveredDevice.STATUS_OFFLINE),
        ("fault", DiscoveredDevice.STATUS_ERROR),
        ("discovered", DiscoveredDevice.STATUS_PENDING),
    ],
)
def test_generic_status_normalization(status: str, expected_status: str) -> None:
    _, _, _, normalized = DiscoveryOrchestrationService._extract_generic_fields({"status": status})

    assert normalized == expected_status


def test_broadcast_failure_does_not_fail_discovery() -> None:
    manufacturer = ManufacturerFactory()

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update",
        side_effect=RuntimeError("channel layer unavailable"),
    ):
        DiscoveryOrchestrationService._emit_refresh_broadcast(manufacturer, [{}])
