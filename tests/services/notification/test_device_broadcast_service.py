"""Bounded, resumable device projection broadcast contracts."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache

import pytest

from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.notification.device_broadcast_dtos import DeviceBroadcastCursor
from micboard.services.notification.device_broadcast_service import (
    DEVICE_BROADCAST_CURSOR_TIMEOUT_SECONDS,
    DeviceSnapshotBroadcastService,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _cursor_key(manufacturer_id: int, namespace: str = "test") -> str:
    return DeviceSnapshotBroadcastService._cursor_key(
        manufacturer_id,
        namespace=namespace,
    )


def test_broadcast_resumes_bounded_windows_with_one_snapshot_identity() -> None:
    """Later rows are resumed on the next call without exceeding either hard budget."""
    manufacturer = ManufacturerFactory(code="bounded-broadcast")
    chassis = [
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=f"device-{number}",
            ip=f"192.0.2.{number + 1}",
            status="online",
        )
        for number in range(5)
    ]
    WirelessChassisFactory(manufacturer=manufacturer, status="offline")
    cache.delete(_cursor_key(manufacturer.pk))

    with patch.object(BroadcastService, "broadcast_device_update") as broadcast:
        first = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="test",
            max_devices=3,
            chunk_size=2,
            statuses=("online",),
        )
        first_payloads = [item.kwargs["data"] for item in broadcast.call_args_list]
        broadcast.reset_mock()
        second = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="test",
            max_devices=3,
            chunk_size=2,
            statuses=("online",),
        )
        second_payloads = [item.kwargs["data"] for item in broadcast.call_args_list]

    assert first.rows_sent == 3
    assert first.chunks_sent == 2
    assert first.inventory_complete is False
    assert first.next_cursor == chassis[2].pk
    assert [len(payload["receivers"]) for payload in first_payloads] == [2, 1]
    assert [payload["is_final_chunk"] for payload in first_payloads] == [False, True]
    assert all(payload["inventory_complete"] is False for payload in first_payloads)

    assert second.rows_sent == 2
    assert second.chunks_sent == 1
    assert second.inventory_complete is True
    assert second.next_cursor == 0
    assert [row["id"] for row in second_payloads[0]["receivers"]] == [
        chassis[3].pk,
        chassis[4].pk,
    ]
    assert second_payloads[0]["snapshot_id"] == first_payloads[0]["snapshot_id"]
    assert cache.get(_cursor_key(manufacturer.pk)) == {"after_id": 0, "snapshot_id": ""}


def test_broadcast_emits_one_complete_empty_chunk() -> None:
    """An empty projection still has an explicit, bounded completion event."""
    manufacturer = ManufacturerFactory(code="empty-projection")
    with patch.object(BroadcastService, "broadcast_device_update") as broadcast:
        result = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="empty",
            max_devices=0,
            chunk_size=999_999,
            statuses=None,
        )

    assert result.rows_sent == 0
    assert result.chunks_sent == 1
    assert result.inventory_complete is True
    payload = broadcast.call_args.kwargs["data"]
    assert payload["receivers"] == []
    assert payload["is_final_chunk"] is True
    assert payload["next_cursor"] is None


def test_stale_cursor_restarts_from_the_first_live_row() -> None:
    """Deleted tail rows cannot leave a manufacturer projection permanently empty."""
    manufacturer = ManufacturerFactory(code="stale-cursor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="offline")
    cache.set(
        _cursor_key(manufacturer.pk, "stale"),
        DeviceBroadcastCursor(after_id=chassis.pk + 10_000, snapshot_id="stale").model_dump(),
        timeout=DEVICE_BROADCAST_CURSOR_TIMEOUT_SECONDS,
    )

    with patch.object(BroadcastService, "broadcast_device_update") as broadcast:
        result = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="stale",
            max_devices=2,
            chunk_size=2,
        )

    assert result.rows_sent == 1
    assert result.inventory_complete is True
    payload = broadcast.call_args.kwargs["data"]
    assert payload["receivers"][0]["id"] == chassis.pk
    assert payload["snapshot_id"] != "stale"


@pytest.mark.parametrize("cached_value", ["invalid", {"after_id": -1, "snapshot_id": "bad"}])
def test_invalid_cursor_values_fail_safe(cached_value: object) -> None:
    """Malformed shared-cache state is ignored without suppressing the broadcast."""
    manufacturer = ManufacturerFactory(code="invalid-cursor")
    WirelessChassisFactory(manufacturer=manufacturer)
    with (
        patch(
            "micboard.services.notification.device_broadcast_service.cache.get",
            return_value=cached_value,
        ),
        patch("micboard.services.notification.device_broadcast_service.cache.set"),
        patch.object(BroadcastService, "broadcast_device_update"),
    ):
        result = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="invalid",
            max_devices=1,
            chunk_size=1,
        )

    assert result.rows_sent == 1


def test_cache_outage_does_not_disclose_details_or_suppress_broadcast(caplog) -> None:
    """Cursor storage is optional and its exception text is redacted."""
    manufacturer = ManufacturerFactory(code="cache-outage")
    WirelessChassisFactory(manufacturer=manufacturer)
    secret = "redis://private-credential"
    with (
        patch(
            "micboard.services.notification.device_broadcast_service.cache.get",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.notification.device_broadcast_service.cache.set",
            side_effect=RuntimeError(secret),
        ),
        patch.object(BroadcastService, "broadcast_device_update") as broadcast,
    ):
        result = DeviceSnapshotBroadcastService.broadcast(
            manufacturer=manufacturer,
            namespace="outage",
            max_devices=1,
            chunk_size=1,
        )

    assert result.rows_sent == 1
    broadcast.assert_called_once()
    assert secret not in caplog.text


def test_projection_serialization_bounds_private_address_types() -> None:
    """Nullable addresses retain the stable browser payload shape."""
    assert (
        DeviceSnapshotBroadcastService._serialize(
            {
                "id": 1,
                "api_device_id": "device",
                "name": "Receiver",
                "ip": None,
                "status": "offline",
                "model": "RX",
            }
        )["ip"]
        is None
    )
