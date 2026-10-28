"""Bounded alert evaluation after a manufacturer poll."""

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.monitoring.alert_fanout_dtos import (
    HARD_ALERT_MAX_ASSIGNMENTS,
    HARD_ALERT_MAX_DELIVERIES,
    HARD_ALERT_MAX_RECIPIENTS,
    AlertFanoutBudget,
)
from micboard.services.monitoring.alerts import alert_manager
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.shared.fair_page_cursor import (
    fair_page,
    flag_cursor,
    position_cursor,
    read_cursor,
    write_cursor,
)
from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)

DEFAULT_POLL_ALERT_MAX_UNITS = 100
HARD_POLL_ALERT_MAX_UNITS = 500
POLL_ALERT_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
_SCAN_CURSOR = position_cursor("alert scan cursor", timeout=POLL_ALERT_CURSOR_TIMEOUT_SECONDS)
_SCOPE_CURSOR = flag_cursor("alert scope cursor", timeout=POLL_ALERT_CURSOR_TIMEOUT_SECONDS)


class PollAlertScanResult(PydanticBaseDTO):
    """Bounded outcome of evaluating alert-eligible wireless units."""

    scanned: int = Field(ge=0, le=HARD_POLL_ALERT_MAX_UNITS)
    failed: int = Field(ge=0, le=HARD_POLL_ALERT_MAX_UNITS)
    truncated: bool
    units_truncated: bool
    limit: int = Field(ge=1, le=HARD_POLL_ALERT_MAX_UNITS)
    assignments_evaluated: int = Field(ge=0, le=HARD_ALERT_MAX_ASSIGNMENTS)
    recipients_evaluated: int = Field(ge=0, le=HARD_ALERT_MAX_RECIPIENTS)
    delivery_attempts: int = Field(ge=0, le=HARD_ALERT_MAX_DELIVERIES)
    assignments_truncated: bool
    recipients_truncated: bool
    deliveries_truncated: bool


class PollAlertService:
    """Evaluate alerts for a fair, deterministic, bounded unit inventory."""

    @classmethod
    def evaluate_manufacturer(cls, manufacturer: Manufacturer) -> PollAlertScanResult:
        """Evaluate assigned units without allowing an unbounded post-poll scan."""
        limit = cls._scan_limit()
        cursor = read_cursor(_SCAN_CURSOR, cls._cursor_key(manufacturer.pk))
        candidates = WirelessUnit.objects.filter(
            manufacturer=manufacturer,
            performer_assignments__is_active=True,
            performer_assignments__monitoring_group__is_active=True,
            performer_assignments__monitoring_group__users__is_active=True,
        ).distinct()
        bounded_units, truncated = fair_page(candidates, after_pk=cursor, limit=limit)

        failed = 0
        scanned = 0
        budget = AlertFanoutBudget.from_settings()
        transmitter_first = read_cursor(_SCOPE_CURSOR, cls._scope_cursor_key(manufacturer.pk))
        checks = (
            (
                alert_manager.check_wireless_unit_alerts,
                alert_manager.check_hardware_offline_alerts,
            )
            if transmitter_first
            else (
                alert_manager.check_hardware_offline_alerts,
                alert_manager.check_wireless_unit_alerts,
            )
        )
        if bounded_units:
            write_cursor(
                _SCOPE_CURSOR,
                cls._scope_cursor_key(manufacturer.pk),
                not transmitter_first,
            )

        for unit in bounded_units:
            try:
                for check in checks:
                    check(unit, budget=budget)
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Alert evaluation failed for wireless unit %s",
                    unit.pk,
                    exc_info=sanitized_exception_info(exc),
                )
            finally:
                scanned += 1
                write_cursor(_SCAN_CURSOR, cls._cursor_key(manufacturer.pk), unit.pk)

            if budget.truncated or budget.exhausted:
                break

        units_truncated = truncated or scanned < len(bounded_units)

        if units_truncated:
            logger.warning(
                "Alert evaluation truncated for manufacturer %s after %d wireless units",
                manufacturer.pk,
                scanned,
            )

        return PollAlertScanResult(
            scanned=scanned,
            failed=failed,
            truncated=units_truncated or budget.truncated,
            units_truncated=units_truncated,
            limit=limit,
            assignments_evaluated=budget.assignments_evaluated,
            recipients_evaluated=budget.recipients_evaluated,
            delivery_attempts=budget.delivery_attempts,
            assignments_truncated=budget.assignments_truncated,
            recipients_truncated=budget.recipients_truncated,
            deliveries_truncated=budget.deliveries_truncated,
        )

    @staticmethod
    def _cursor_key(manufacturer_id: int) -> str:
        return f"micboard:poll-alert-cursor:v1:{manufacturer_id}"

    @staticmethod
    def _scope_cursor_key(manufacturer_id: int) -> str:
        return f"micboard:poll-alert-scope:v1:{manufacturer_id}"

    @staticmethod
    def _scan_limit() -> int:
        """Return how many units one alert poll may scan, clamped to the package hard ceiling."""
        raw_limit = micboard_settings.get(
            "MICBOARD_POLL_ALERT_MAX_UNITS",
            DEFAULT_POLL_ALERT_MAX_UNITS,
        )
        if isinstance(raw_limit, bool):
            return DEFAULT_POLL_ALERT_MAX_UNITS
        try:
            parsed_limit = int(raw_limit)
        except TypeError, ValueError:
            return DEFAULT_POLL_ALERT_MAX_UNITS
        return min(max(parsed_limit, 1), HARD_POLL_ALERT_MAX_UNITS)
