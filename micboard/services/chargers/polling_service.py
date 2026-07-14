"""Bounded service-layer workflow for charger dashboard snapshots."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping, Sequence
from itertools import islice
from typing import Any

from django.conf import settings
from django.core.cache import cache

from pydantic import ValidationError

from micboard.services.chargers.polling_dtos import (
    ChargerInventoryPage,
    ChargerPollingCursor,
    ChargerPollingLimits,
    ChargerPollResult,
    ChargerSlotSnapshot,
    ChargerStationSnapshot,
)
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARGER_DEVICES = 100
DEFAULT_MAX_CHARGER_STATIONS = 64
DEFAULT_MAX_CHARGER_SLOTS = 32
HARD_MAX_CHARGER_DEVICES = 500
HARD_MAX_CHARGER_STATIONS = 256
HARD_MAX_CHARGER_SLOTS = 128
# A full materialized inventory is fingerprinted once per page. Reject larger
# plugin results before iteration so hashing and cursor validation remain bounded.
HARD_MAX_CHARGER_INVENTORY_SIZE = 5_000
CHARGER_POLL_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60

CHARGING_STATION_MODELS = frozenset({"SBC250", "SBC850", "MXWNCS8", "MXWNCS4", "SBC220"})


class ChargerPollingService:
    """Build and cache one bounded manufacturer charger snapshot."""

    @classmethod
    def poll(cls, manufacturer: Any) -> ChargerPollResult:
        """Poll supported stations without unbounded inventory or channel work."""
        limits = cls.limits()
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        cursor = cls._read_cursor(manufacturer)
        inventory_page = cls._inventory_page(
            plugin.get_devices(),
            limits.max_devices,
            start_offset=cursor.next_offset,
            expected_inventory_size=cursor.inventory_size if cursor.next_offset else None,
            expected_inventory_fingerprint=(
                cursor.inventory_fingerprint if cursor.next_offset else None
            ),
        )

        try:
            is_healthy = bool(plugin.get_client().is_healthy())
        except Exception as exc:
            logger.exception(
                "Could not read charger service health for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            is_healthy = False

        continuing_cycle = inventory_page.start_offset != 0
        accumulated, cursor_rebounded = cls._station_accumulator(
            () if inventory_page.start_offset == 0 else cursor.stations,
            limits.max_stations,
        )
        stations_truncated = cursor_rebounded or (
            cursor.stations_truncated if continuing_cycle else False
        )
        failed_count = 0
        slots_truncated = cursor.slots_truncated if continuing_cycle else False
        cycle_failed = cursor.cycle_failed if continuing_cycle else False
        for raw_device in inventory_page.items:
            if not cls._is_station(raw_device):
                continue

            device_id = cls._bounded_text(raw_device.get("api_device_id"), 255)
            if not device_id:
                failed_count += 1
                continue
            if device_id in accumulated:
                continue
            if len(accumulated) >= limits.max_stations:
                # Keep a stable prefix: rotating station cohorts would make each
                # complete public snapshot appear to delete still-live stations.
                stations_truncated = True
                continue

            station_slots, channel_truncated, channel_failed = cls._station_slots(
                plugin,
                device_id=device_id,
                limit=limits.max_slots,
            )
            slots_truncated = slots_truncated or channel_truncated
            if channel_failed:
                failed_count += 1
                cycle_failed = True
                continue

            accumulated[device_id] = ChargerStationSnapshot(
                id=device_id,
                name=cls._bounded_text(raw_device.get("name"), 200) or "Charger",
                status="online" if is_healthy else "offline",
                slots=station_slots,
            )

        stations = [
            station.model_copy(update={"status": "online" if is_healthy else "offline"})
            for station in accumulated.values()
        ]
        if inventory_page.cycle_complete:
            cls._finish_cycle(
                manufacturer,
                stations=stations,
                publish=not cycle_failed,
            )
        else:
            cls._persist_continuation(
                manufacturer,
                inventory_page=inventory_page,
                stations=stations,
                stations_truncated=stations_truncated,
                slots_truncated=slots_truncated,
                cycle_failed=cycle_failed,
            )

        return ChargerPollResult(
            scanned_count=len(inventory_page.items),
            cached_count=len(stations),
            failed_count=failed_count,
            inventory_truncated=inventory_page.inventory_truncated,
            stations_truncated=stations_truncated,
            slots_truncated=slots_truncated,
        )

    @staticmethod
    def limits() -> ChargerPollingLimits:
        """Resolve host settings under immutable package ceilings."""
        return ChargerPollingLimits(
            max_devices=_bounded_setting(
                "MICBOARD_CHARGER_MAX_DEVICES",
                DEFAULT_MAX_CHARGER_DEVICES,
                HARD_MAX_CHARGER_DEVICES,
            ),
            max_stations=_bounded_setting(
                "MICBOARD_CHARGER_MAX_STATIONS",
                DEFAULT_MAX_CHARGER_STATIONS,
                HARD_MAX_CHARGER_STATIONS,
            ),
            max_slots=_bounded_setting(
                "MICBOARD_CHARGER_MAX_SLOTS",
                DEFAULT_MAX_CHARGER_SLOTS,
                HARD_MAX_CHARGER_SLOTS,
            ),
        )

    @staticmethod
    def _bounded_items(value: object, limit: int) -> tuple[list[Mapping[str, Any]], bool]:
        """Consume at most one item beyond a limit from an arbitrary vendor iterable."""
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
            return [], False
        bounded = list(islice(value, limit + 1))
        return (
            [item for item in bounded[:limit] if isinstance(item, Mapping)],
            len(bounded) > limit,
        )

    @classmethod
    def _station_slots(
        cls,
        plugin: Any,
        *,
        device_id: str,
        limit: int,
    ) -> tuple[list[ChargerSlotSnapshot], bool, bool]:
        """Return one bounded station slot set and contain vendor failures."""
        try:
            raw_channels, truncated = cls._bounded_items(
                plugin.get_device_channels(device_id),
                limit,
            )
        except Exception as exc:
            logger.exception(
                "Could not read charger channels; device identifier redacted",
                exc_info=sanitized_exception_info(exc),
            )
            return [], False, True

        slots = [
            slot for channel in raw_channels if (slot := cls._slot_snapshot(channel)) is not None
        ]
        return slots, truncated, False

    @classmethod
    def _finish_cycle(
        cls,
        manufacturer: Any,
        *,
        stations: list[ChargerStationSnapshot],
        publish: bool,
    ) -> None:
        """Publish only complete station data, then discard continuation state."""
        if publish:
            cls._publish_snapshot(manufacturer, stations)
        cls._clear_cursor(manufacturer)

    @classmethod
    def _persist_continuation(
        cls,
        manufacturer: Any,
        *,
        inventory_page: ChargerInventoryPage,
        stations: list[ChargerStationSnapshot],
        stations_truncated: bool,
        slots_truncated: bool,
        cycle_failed: bool,
    ) -> None:
        """Persist only resumable pages while retaining the last public snapshot."""
        if (
            inventory_page.next_offset
            and inventory_page.inventory_size is not None
            and inventory_page.inventory_fingerprint is not None
        ):
            cls._write_cursor(
                manufacturer,
                ChargerPollingCursor(
                    next_offset=inventory_page.next_offset,
                    inventory_size=inventory_page.inventory_size,
                    inventory_fingerprint=inventory_page.inventory_fingerprint,
                    stations=stations,
                    stations_truncated=stations_truncated,
                    slots_truncated=slots_truncated,
                    cycle_failed=cycle_failed,
                ),
            )
            return

        # A one-shot iterable cannot be resumed safely. Preserve the last complete
        # public snapshot instead of replacing it with a partial first page.
        cls._clear_cursor(manufacturer)

    @classmethod
    def _inventory_page(
        cls,
        value: object,
        limit: int,
        *,
        start_offset: int,
        expected_inventory_size: int | None,
        expected_inventory_fingerprint: str | None,
    ) -> ChargerInventoryPage:
        """Return a bounded list page while retaining a safe fallback for invalid plugins."""
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            total = len(value)
            if total > HARD_MAX_CHARGER_INVENTORY_SIZE:
                return ChargerInventoryPage(
                    items=[],
                    start_offset=0,
                    next_offset=0,
                    inventory_size=total,
                    inventory_truncated=True,
                    cycle_complete=False,
                )
            inventory_fingerprint = cls._inventory_fingerprint(value)
            inventory_unchanged = expected_inventory_size in (None, total) and (
                expected_inventory_fingerprint in (None, inventory_fingerprint)
            )
            normalized_offset = (
                start_offset if inventory_unchanged and 0 <= start_offset < total else 0
            )
            next_offset = min(normalized_offset + limit, total)
            raw_items = value[normalized_offset:next_offset]
            return ChargerInventoryPage(
                items=cls._inventory_items(raw_items, limit),
                start_offset=normalized_offset,
                next_offset=0 if next_offset >= total else next_offset,
                inventory_size=total,
                inventory_fingerprint=inventory_fingerprint,
                inventory_truncated=total > limit,
                cycle_complete=next_offset >= total,
            )

        items, truncated = cls._bounded_items(value, limit)
        return ChargerInventoryPage(
            items=cls._inventory_items(items, limit),
            start_offset=0,
            next_offset=0,
            inventory_truncated=truncated,
            cycle_complete=not truncated,
        )

    @classmethod
    def _inventory_fingerprint(cls, items: Sequence[object]) -> str:
        """Hash bounded identity fields so a cursor cannot cross inventory versions."""
        digest = hashlib.sha256()
        digest.update(str(len(items)).encode("ascii"))
        for item in items:
            digest.update(b"\x00M" if isinstance(item, Mapping) else b"\x00X")
            for field_name in ("api_device_id", "model", "device_type"):
                raw_value = item.get(field_name) if isinstance(item, Mapping) else None
                value = cls._bounded_text(raw_value, 255)
                encoded = value.encode("utf-8")
                digest.update(len(encoded).to_bytes(2, byteorder="big"))
                digest.update(encoded)
        return digest.hexdigest()

    @staticmethod
    def _inventory_items(items: Iterable[object], limit: int) -> list[dict[str, Any]]:
        """Copy only fields consumed by polling from already bounded inventory rows."""
        return [
            {
                "api_device_id": item.get("api_device_id"),
                "model": item.get("model"),
                "device_type": item.get("device_type"),
                "name": item.get("name"),
            }
            for item in islice(items, limit)
            if isinstance(item, Mapping)
        ]

    @staticmethod
    def _station_accumulator(
        stations: Iterable[ChargerStationSnapshot],
        limit: int,
    ) -> tuple[dict[str, ChargerStationSnapshot], bool]:
        """Restore unique cursor stations in deterministic order under the current limit."""
        accumulated: dict[str, ChargerStationSnapshot] = {}
        truncated = False
        for station in stations:
            if station.id in accumulated:
                continue
            if len(accumulated) >= limit:
                truncated = True
                continue
            accumulated[station.id] = station
        return accumulated, truncated

    @staticmethod
    def _cursor_key(manufacturer: Any) -> str:
        return f"micboard:charger-poll:v1:{manufacturer.pk}:{manufacturer.code}"

    @classmethod
    def _read_cursor(cls, manufacturer: Any) -> ChargerPollingCursor:
        """Read validated continuation state without making polling cache-dependent."""
        try:
            value = cache.get(cls._cursor_key(manufacturer))
        except Exception as exc:
            logger.exception(
                "Could not read charger polling cursor for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            value = None
        try:
            return ChargerPollingCursor.model_validate(value)
        except (TypeError, ValidationError):
            return ChargerPollingCursor(next_offset=0, inventory_size=0, stations=[])

    @classmethod
    def _write_cursor(cls, manufacturer: Any, cursor: ChargerPollingCursor) -> None:
        """Persist a partial bounded cycle while tolerating shared-cache outages."""
        try:
            cache.set(
                cls._cursor_key(manufacturer),
                cursor.model_dump(exclude_defaults=True),
                timeout=CHARGER_POLL_CURSOR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Could not persist charger polling cursor for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    def _clear_cursor(cls, manufacturer: Any) -> None:
        """Clear completed continuation state without failing a successful poll."""
        try:
            cache.delete(cls._cursor_key(manufacturer))
        except Exception as exc:
            logger.exception(
                "Could not clear charger polling cursor for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @staticmethod
    def _publish_snapshot(
        manufacturer: Any,
        stations: list[ChargerStationSnapshot],
    ) -> None:
        """Atomically replace the public snapshot only after a full inventory cycle."""
        try:
            cache.set(
                f"charger_data_{manufacturer.code}",
                [station.model_dump() for station in stations],
                timeout=60,
            )
        except Exception as exc:
            logger.exception(
                "Could not cache charger snapshot for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    def _is_station(cls, device: Mapping[str, Any]) -> bool:
        device_id = device.get("api_device_id")
        model = cls._bounded_text(device.get("model"), 255)
        device_type = cls._bounded_text(device.get("device_type"), 255)
        return (
            isinstance(device_id, str)
            and bool(device_id)
            and (model in CHARGING_STATION_MODELS or device_type in CHARGING_STATION_MODELS)
        )

    @classmethod
    def _slot_snapshot(cls, channel: Mapping[str, Any]) -> ChargerSlotSnapshot | None:
        tx_data = channel.get("tx")
        if not isinstance(tx_data, Mapping):
            return None
        return ChargerSlotSnapshot(
            slot_number=cls._bounded_integer(channel.get("channel"), minimum=0, maximum=1024),
            mic_name=cls._bounded_text(tx_data.get("name"), 200) or "Unknown Mic",
            battery_level=cls._bounded_integer(
                tx_data.get("battery_percentage"),
                minimum=0,
                maximum=100,
            ),
            charging=bool(tx_data.get("charging_status", False)),
        )

    @staticmethod
    def _bounded_integer(value: object, *, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            return minimum
        if not isinstance(value, (int, float, str)):
            return minimum
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return minimum
        return min(max(parsed, minimum), maximum)

    @staticmethod
    def _bounded_text(value: object, maximum: int) -> str:
        if not isinstance(value, str):
            return ""
        return "".join(
            character for character in value[:maximum] if character.isprintable()
        ).strip()


def _bounded_setting(name: str, default: int, hard_limit: int) -> int:
    raw_value = getattr(settings, name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), hard_limit)
