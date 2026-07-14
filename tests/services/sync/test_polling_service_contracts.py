"""Contracts for the supported single-manufacturer polling service."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

from django.test import override_settings

import pytest

from micboard.services.notification.device_broadcast_dtos import DeviceBroadcastResult
from micboard.services.notification.device_broadcast_service import (
    DeviceSnapshotBroadcastService,
)
from micboard.services.sync.hardware_sync_service import HardwareSyncService
from micboard.services.sync.polling_service import PollingService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def _manufacturer(code: str = "test") -> Any:
    return SimpleNamespace(pk=7, code=code, name=code.title())


@patch(
    "micboard.services.sync.hardware_sync_service."
    "ManufacturerSyncService.sync_devices_for_manufacturer"
)
def test_hardware_sync_preserves_inventory_limit_metadata(sync_manufacturer: MagicMock) -> None:
    """The compatibility service retains bounded-inventory metadata for task callers."""
    sync_manufacturer.return_value = {
        "success": False,
        "devices_added": 0,
        "devices_updated": 0,
        "devices_removed": 0,
        "errors": ["inventory incomplete"],
        "devices_examined": 501,
        "device_limit": 500,
        "inventory_complete": False,
    }

    result = HardwareSyncService.sync_devices(manufacturer_code="test", force=True)

    assert result["devices_examined"] == 501
    assert result["device_limit"] == 500
    assert result["inventory_complete"] is False
    sync_manufacturer.assert_called_once_with(manufacturer_code="test", force=True)


@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_broadcasts_persisted_state_once(sync_devices: MagicMock) -> None:
    manufacturer = _manufacturer()
    sync_devices.return_value = {"created": 2, "updated": 1, "errors": 0}
    service = cast(Any, PollingService())
    service.broadcast_device_updates = Mock()

    result = service.poll_manufacturer(manufacturer)

    assert result["devices_created"] == 2
    assert result["devices_updated"] == 1
    sync_devices.assert_called_once_with(manufacturer_code="test", force=False)
    service.broadcast_device_updates.assert_called_once_with(manufacturer, result)


@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_propagates_explicit_force(sync_devices: MagicMock) -> None:
    """The operator force override reaches the locked persistence boundary."""
    manufacturer = _manufacturer()
    sync_devices.return_value = {"created": 0, "updated": 0, "errors": 0}
    service = cast(Any, PollingService())
    service.broadcast_device_updates = Mock()

    service.poll_manufacturer(manufacturer, force=True)

    sync_devices.assert_called_once_with(manufacturer_code="test", force=True)


@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_propagates_incomplete_inventory(sync_devices: MagicMock) -> None:
    """The Huey-facing result exposes fail-closed vendor inventory overflow."""
    manufacturer = _manufacturer()
    sync_devices.return_value = {
        "created": 0,
        "updated": 0,
        "errors": 1,
        "devices_examined": 501,
        "device_limit": 500,
        "inventory_complete": False,
    }
    service = cast(Any, PollingService())
    service.broadcast_device_updates = Mock()

    result = service.poll_manufacturer(manufacturer)

    assert result["inventory_complete"] is False
    assert result["devices_examined"] == 501
    assert result["device_limit"] == 500
    service.broadcast_device_updates.assert_not_called()


@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_redacts_sync_failure(
    sync_devices: MagicMock,
    caplog,
) -> None:
    secret = "private-vendor-token"
    sync_devices.side_effect = RuntimeError(secret)

    result = PollingService().poll_manufacturer(_manufacturer())

    assert result["status"] == "failed"
    assert result["errors"] == ["RuntimeError: polling failed"]
    assert secret not in caplog.text


@patch.object(DeviceSnapshotBroadcastService, "broadcast")
def test_device_broadcast_delegates_to_bounded_projection_service(
    broadcast: MagicMock,
) -> None:
    broadcast.return_value = DeviceBroadcastResult(
        rows_sent=1,
        chunks_sent=1,
        inventory_complete=True,
        next_cursor=0,
    )
    manufacturer = _manufacturer()

    PollingService().broadcast_device_updates(manufacturer, {})

    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        namespace="poll",
        max_devices=500,
        chunk_size=100,
        statuses=["online", "degraded", "provisioning"],
    )


@pytest.mark.django_db
@override_settings(MICBOARD_POLL_BROADCAST_CHUNK_SIZE=2)
@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
def test_device_broadcast_chunks_full_inventory_with_explicit_final_marker(
    broadcast: MagicMock,
) -> None:
    """Full-fleet snapshots never place more than the configured rows in one event."""
    manufacturer = ManufacturerFactory(code="chunked")
    for number in range(5):
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=f"device-{number}",
            ip=f"192.0.2.{number + 1}",
            status="online",
        )
    WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="offline-device",
        ip="192.0.2.99",
        status="offline",
    )

    PollingService().broadcast_device_updates(manufacturer, {})

    payloads = [call.kwargs["data"] for call in broadcast.call_args_list]
    assert [len(payload["receivers"]) for payload in payloads] == [2, 2, 1]
    assert [payload["chunk_index"] for payload in payloads] == [0, 1, 2]
    assert [payload["is_final_chunk"] for payload in payloads] == [False, False, True]
    assert all(payload["inventory_complete"] is True for payload in payloads)
    assert len({payload["snapshot_id"] for payload in payloads}) == 1


@pytest.mark.django_db
@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
def test_device_broadcast_emits_final_empty_snapshot(
    broadcast: MagicMock,
) -> None:
    """An empty fleet still tells clients that the replacement snapshot is complete."""
    manufacturer = ManufacturerFactory(code="empty-broadcast")

    PollingService().broadcast_device_updates(manufacturer, {})

    payload = broadcast.call_args.kwargs["data"]
    assert payload["receivers"] == []
    assert payload["chunk_index"] == 0
    assert payload["is_final_chunk"] is True
    assert payload["inventory_complete"] is True
