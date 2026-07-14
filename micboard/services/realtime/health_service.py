"""Bounded maintenance and status aggregation for real-time connections."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone

from micboard.models.realtime import RealTimeConnection
from micboard.services.realtime.health_dtos import (
    RealtimeConnectionHealthResult,
    RealtimeConnectionStatusSummary,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_SWEEP = 500
STALE_CONNECTION_MESSAGE = "Connection appears stale - no messages received"


class RealtimeConnectionHealthService:
    """Maintain connection state without unbounded per-row work."""

    @classmethod
    def cleanup(cls) -> RealtimeConnectionHealthResult:
        """Transition bounded oldest-first stale/error rows using bulk updates."""
        now = timezone.now()
        stale_ids, stale_truncated = cls._bounded_ids(
            RealTimeConnection.objects.filter(
                status="connected",
                last_message_at__lt=now - timedelta(minutes=10),
            ).order_by("last_message_at", "pk")
        )
        stale_disconnected = RealTimeConnection.objects.filter(pk__in=stale_ids).update(
            status="disconnected",
            disconnected_at=now,
            error_message=STALE_CONNECTION_MESSAGE,
            error_count=F("error_count") + 1,
            last_error_at=now,
            updated_at=now,
        )

        error_ids, error_truncated = cls._bounded_ids(
            RealTimeConnection.objects.filter(
                status="error",
                last_error_at__lt=now - timedelta(hours=1),
            ).order_by("last_error_at", "pk")
        )
        errors_reset = RealTimeConnection.objects.filter(pk__in=error_ids).update(
            status="disconnected",
            disconnected_at=now,
            error_count=0,
            error_message="",
            updated_at=now,
        )

        counts = cls._status_counts()
        return RealtimeConnectionHealthResult(
            stale_disconnected=stale_disconnected,
            errors_reset=errors_reset,
            active=counts["connected"],
            errors=counts["error"],
            stale_truncated=stale_truncated,
            error_truncated=error_truncated,
        )

    @classmethod
    def summarize(cls) -> RealtimeConnectionStatusSummary:
        """Return one typed aggregate, redacting database exception details."""
        try:
            counts = cls._status_counts()
        except Exception as exc:
            logger.exception(
                "Error getting real-time connection status",
                exc_info=sanitized_exception_info(exc),
            )
            return RealtimeConnectionStatusSummary(
                failed=True,
                error_type=type(exc).__name__,
            )

        total = counts["total"]
        return RealtimeConnectionStatusSummary(
            total=total,
            connected=counts["connected"],
            connecting=counts["connecting"],
            disconnected=counts["disconnected"],
            error=counts["error"],
            stopped=counts["stopped"],
            healthy_percentage=(counts["connected"] / total * 100) if total else 0.0,
        )

    @staticmethod
    def _status_counts() -> dict[str, int]:
        """Aggregate every supported state in one database query."""
        result = RealTimeConnection.objects.aggregate(
            total=Count("pk"),
            connected=Count("pk", filter=Q(status="connected")),
            connecting=Count("pk", filter=Q(status="connecting")),
            disconnected=Count("pk", filter=Q(status="disconnected")),
            error=Count("pk", filter=Q(status="error")),
            stopped=Count("pk", filter=Q(status="stopped")),
        )
        return {key: int(value or 0) for key, value in result.items()}

    @staticmethod
    def _bounded_ids(
        queryset: QuerySet[RealTimeConnection],
    ) -> tuple[list[int], bool]:
        """Return an oldest-first batch plus whether eligible rows remain."""
        ids = list(queryset.values_list("pk", flat=True)[: MAX_CONNECTIONS_PER_SWEEP + 1])
        return ids[:MAX_CONNECTIONS_PER_SWEEP], len(ids) > MAX_CONNECTIONS_PER_SWEEP
