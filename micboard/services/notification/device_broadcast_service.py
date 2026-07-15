"""Bounded, resumable realtime projection broadcasts."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator, Mapping, Sequence
from itertools import islice
from typing import TYPE_CHECKING, Any

from django.core.cache import cache
from django.utils import timezone

from pydantic import ValidationError

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.notification.device_broadcast_dtos import (
    MAX_DEVICE_BROADCAST_ROWS,
    DeviceBroadcastCursor,
    DeviceBroadcastResult,
)
from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)

DEVICE_BROADCAST_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
DEVICE_BROADCAST_FIELDS = ("id", "api_device_id", "name", "ip", "status", "model")


class DeviceSnapshotBroadcastService:
    """Publish at most one configured window of a manufacturer's chassis."""

    @classmethod
    def broadcast(
        cls,
        *,
        manufacturer: Manufacturer,
        namespace: str,
        max_devices: int,
        chunk_size: int,
        statuses: Sequence[str] | None = None,
    ) -> DeviceBroadcastResult:
        """Send one resumable, hard-bounded projection batch."""
        max_devices = min(max(max_devices, 1), MAX_DEVICE_BROADCAST_ROWS)
        chunk_size = min(max(chunk_size, 1), max_devices)
        state = cls._read_cursor(manufacturer.pk, namespace=namespace)
        rows, state = cls._load_rows(
            manufacturer=manufacturer,
            statuses=statuses,
            state=state,
            max_devices=max_devices,
        )
        inventory_complete = len(rows) <= max_devices
        bounded_rows = rows[:max_devices]
        next_cursor = int(bounded_rows[-1]["id"]) if bounded_rows and not inventory_complete else 0
        snapshot_id = state.snapshot_id or secrets.token_urlsafe(12)
        timestamp = timezone.now().isoformat()
        chunks_sent = 0

        for chunk_index, (chunk, is_final) in enumerate(
            cls._iter_chunks(iter(bounded_rows), chunk_size=chunk_size)
        ):
            BroadcastService.broadcast_device_update(
                manufacturer=manufacturer,
                data={
                    "manufacturer_code": manufacturer.code,
                    "receivers": [cls._serialize(row) for row in chunk],
                    "timestamp": timestamp,
                    "snapshot_id": snapshot_id,
                    "chunk_index": chunk_index,
                    "is_final_chunk": is_final,
                    "inventory_complete": inventory_complete,
                    "next_cursor": next_cursor or None,
                    "broadcast_namespace": namespace,
                },
            )
            chunks_sent += 1

        cls._write_cursor(
            manufacturer.pk,
            namespace=namespace,
            state=DeviceBroadcastCursor(
                after_id=next_cursor,
                snapshot_id=snapshot_id if next_cursor else "",
            ),
        )
        return DeviceBroadcastResult(
            rows_sent=len(bounded_rows),
            chunks_sent=chunks_sent,
            inventory_complete=inventory_complete,
            next_cursor=next_cursor,
        )

    @classmethod
    def _load_rows(
        cls,
        *,
        manufacturer: Manufacturer,
        statuses: Sequence[str] | None,
        state: DeviceBroadcastCursor,
        max_devices: int,
    ) -> tuple[list[Mapping[str, Any]], DeviceBroadcastCursor]:
        queryset = WirelessChassis.objects.filter(manufacturer=manufacturer)
        if statuses is not None:
            queryset = queryset.filter(status__in=tuple(statuses))
        projection = queryset.order_by("pk").values(*DEVICE_BROADCAST_FIELDS)
        if state.after_id:
            rows = list(projection.filter(pk__gt=state.after_id)[: max_devices + 1])
            if rows:
                return rows, state
            state = DeviceBroadcastCursor()
        return list(projection[: max_devices + 1]), state

    @staticmethod
    def _serialize(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "api_device_id": row["api_device_id"],
            "name": row["name"],
            "ip": str(row["ip"]) if row["ip"] else None,
            "status": row["status"],
            "model": row["model"],
        }

    @staticmethod
    def _iter_chunks(
        rows: Iterator[Mapping[str, Any]],
        *,
        chunk_size: int,
    ) -> Iterator[tuple[list[Mapping[str, Any]], bool]]:
        iterator = iter(rows)
        current = list(islice(iterator, chunk_size))
        if not current:
            yield [], True
            return
        while current:
            following = list(islice(iterator, chunk_size))
            yield current, not following
            current = following

    @staticmethod
    def _cursor_key(manufacturer_id: int, *, namespace: str) -> str:
        return f"micboard:device-broadcast-cursor:v1:{namespace}:{manufacturer_id}"

    @classmethod
    def _read_cursor(cls, manufacturer_id: int, *, namespace: str) -> DeviceBroadcastCursor:
        try:
            value = cache.get(cls._cursor_key(manufacturer_id, namespace=namespace))
            if value is None:
                return DeviceBroadcastCursor()
            return DeviceBroadcastCursor.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            return DeviceBroadcastCursor()
        except Exception as exc:
            logger.exception(
                "Could not read device broadcast cursor for manufacturer %s",
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            return DeviceBroadcastCursor()

    @classmethod
    def _write_cursor(
        cls,
        manufacturer_id: int,
        *,
        namespace: str,
        state: DeviceBroadcastCursor,
    ) -> None:
        try:
            cache.set(
                cls._cursor_key(manufacturer_id, namespace=namespace),
                state.model_dump(),
                timeout=DEVICE_BROADCAST_CURSOR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Could not persist device broadcast cursor for manufacturer %s",
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
