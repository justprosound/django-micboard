"""Cache adapter for resumable charger polling and published snapshots."""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

from pydantic import ValidationError

from micboard.services.chargers.polling_dtos import (
    ChargerInventoryPage,
    ChargerPollingCursor,
    ChargerStationSnapshot,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

CHARGER_POLL_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
CHARGER_SNAPSHOT_TIMEOUT_SECONDS = 60


class ChargerPollingCacheAdapter:
    """Own cache keys, validation, failure containment, and continuation persistence."""

    @staticmethod
    def cursor_key(manufacturer: Any) -> str:
        """Return the private continuation key for one manufacturer."""
        return f"micboard:charger-poll:v1:{manufacturer.pk}:{manufacturer.code}"

    @staticmethod
    def snapshot_key(manufacturer: Any) -> str:
        """Return the public complete-snapshot key for one manufacturer."""
        return f"charger_data_{manufacturer.code}"

    @classmethod
    def read_cursor(cls, manufacturer: Any) -> ChargerPollingCursor:
        """Read validated continuation state without making polling cache-dependent."""
        try:
            value = cache.get(cls.cursor_key(manufacturer))
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
    def write_cursor(cls, manufacturer: Any, cursor: ChargerPollingCursor) -> None:
        """Persist a partial bounded cycle while tolerating shared-cache outages."""
        try:
            cache.set(
                cls.cursor_key(manufacturer),
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
    def clear_cursor(cls, manufacturer: Any) -> None:
        """Clear completed continuation state without failing a successful poll."""
        try:
            cache.delete(cls.cursor_key(manufacturer))
        except Exception as exc:
            logger.exception(
                "Could not clear charger polling cursor for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    def publish_snapshot(
        cls,
        manufacturer: Any,
        stations: list[ChargerStationSnapshot],
    ) -> None:
        """Atomically replace the public snapshot only after a full inventory cycle."""
        try:
            cache.set(
                cls.snapshot_key(manufacturer),
                [station.model_dump() for station in stations],
                timeout=CHARGER_SNAPSHOT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Could not cache charger snapshot for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    def finish_cycle(
        cls,
        manufacturer: Any,
        *,
        stations: list[ChargerStationSnapshot],
        publish: bool,
    ) -> None:
        """Publish complete station data when safe, then discard continuation state."""
        if publish:
            cls.publish_snapshot(manufacturer, stations)
        cls.clear_cursor(manufacturer)

    @classmethod
    def persist_continuation(
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
            cls.write_cursor(
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
        cls.clear_cursor(manufacturer)
