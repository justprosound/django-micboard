"""Coverage for bounded, secret-safe real-time connection health maintenance."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from micboard.services.realtime import health_service
from micboard.services.realtime.health_service import (
    STALE_CONNECTION_MESSAGE,
    RealtimeConnectionHealthService,
)
from tests.factories.realtime import RealTimeConnectionFactory


@pytest.mark.django_db
def test_cleanup_processes_bounded_oldest_first_batches_without_starvation(
    monkeypatch,
) -> None:
    """Eligible rows leave each queue so later sweeps reach every connection."""
    now = timezone.now()
    monkeypatch.setattr(health_service, "MAX_CONNECTIONS_PER_SWEEP", 2)
    stale = [
        RealTimeConnectionFactory(
            status="connected",
            last_message_at=now - timedelta(minutes=30 - index),
        )
        for index in range(3)
    ]
    errors = [
        RealTimeConnectionFactory(
            status="error",
            last_error_at=now - timedelta(hours=3) + timedelta(minutes=index),
            error_count=4,
            error_message="secret vendor failure",
        )
        for index in range(3)
    ]

    with patch.object(health_service.timezone, "now", return_value=now):
        first = RealtimeConnectionHealthService.cleanup()
        second = RealtimeConnectionHealthService.cleanup()

    assert (first.stale_disconnected, first.errors_reset) == (2, 2)
    assert first.stale_truncated is True
    assert first.error_truncated is True
    assert (second.stale_disconnected, second.errors_reset) == (1, 1)
    assert second.stale_truncated is False
    assert second.error_truncated is False

    for connection in stale:
        connection.refresh_from_db()
        assert connection.status == "disconnected"
        assert connection.error_count == 1
        assert connection.error_message == STALE_CONNECTION_MESSAGE
    for connection in errors:
        connection.refresh_from_db()
        assert connection.status == "disconnected"
        assert connection.error_count == 0
        assert connection.error_message == ""


@pytest.mark.django_db
def test_summary_aggregates_supported_states_and_percentage() -> None:
    """Status output is a typed aggregate rather than a sequence of count queries."""
    for status in ("connected", "connected", "connecting", "disconnected", "error", "stopped"):
        RealTimeConnectionFactory(status=status)

    summary = RealtimeConnectionHealthService.summarize()

    assert summary.model_dump() == {
        "total": 6,
        "connected": 2,
        "connecting": 1,
        "disconnected": 1,
        "error": 1,
        "stopped": 1,
        "healthy_percentage": pytest.approx(100 / 3),
        "failed": False,
        "error_type": None,
    }


@pytest.mark.django_db
def test_summary_redacts_database_exception_details() -> None:
    """Neither the typed result nor sanitized traceback retains secret text."""
    secret = "postgres-password-in-error"
    error = RuntimeError(secret)

    with (
        patch.object(
            health_service.RealTimeConnection.objects,
            "aggregate",
            side_effect=error,
        ),
        patch.object(health_service.logger, "exception") as exception,
    ):
        summary = RealtimeConnectionHealthService.summarize()

    assert summary.failed is True
    assert summary.error_type == "RuntimeError"
    assert secret not in str(summary.model_dump())
    assert exception.call_args.args == ("Error getting real-time connection status",)
    assert secret not in str(exception.call_args.kwargs["exc_info"][1])
