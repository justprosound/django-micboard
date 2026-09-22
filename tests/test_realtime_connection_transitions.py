"""How a realtime connection's state changes.

A connection row moves between connecting, connected, error, disconnected and stopped. Each
transition has one definition, so a row reached through the admin changelist ends up in the
same state as a row reached by the subscription runner.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from micboard.models.realtime.connection import RealTimeConnection
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _connection(**overrides: object) -> RealTimeConnection:
    """Build one connection row in a stale, previously-failed state."""
    values: dict[str, object] = {
        "chassis": WirelessChassisFactory(),
        "connection_type": "sse",
        "status": "error",
        "disconnected_at": timezone.now() - timedelta(hours=1),
        "error_message": "previous failure",
        "error_count": 3,
        "last_error_at": timezone.now() - timedelta(hours=1),
        "reconnect_attempts": 4,
    }
    values.update(overrides)
    return RealTimeConnection.objects.create(**values)


def test_connecting_a_row_clears_every_trace_of_the_previous_failure() -> None:
    """A newly connected row cannot keep a past disconnection or reconnect counter."""
    connection = _connection()

    RealTimeConnection.objects.filter(pk=connection.pk).mark_connected()

    connection.refresh_from_db()
    assert connection.status == "connected"
    assert connection.connected_at is not None
    assert connection.last_message_at is not None
    assert connection.disconnected_at is None
    assert connection.error_count == 0
    assert connection.error_message == ""
    assert connection.reconnect_attempts == 0


def test_a_bulk_transition_applies_to_every_selected_row() -> None:
    """The admin changelist and the runner reach the same transition definition."""
    first = _connection()
    second = _connection()

    updated = RealTimeConnection.objects.filter(pk__in=[first.pk, second.pk]).mark_connected()

    assert updated == 2
    for connection in (first, second):
        connection.refresh_from_db()
        assert connection.disconnected_at is None
        assert connection.reconnect_attempts == 0


def test_recording_a_message_establishes_a_pending_connection() -> None:
    """The first update on a connecting row is what proves the connection is live."""
    connection = _connection(status="connecting")

    RealTimeConnection.objects.filter(pk=connection.pk).record_message()

    connection.refresh_from_db()
    assert connection.status == "connected"
    assert connection.connected_at is not None
    assert connection.error_count == 0


def test_recording_a_message_on_a_live_connection_only_moves_its_clock() -> None:
    """A live connection keeps the moment it was established across later updates."""
    established = timezone.now() - timedelta(minutes=5)
    connection = _connection(status="connected", connected_at=established, error_count=0)

    RealTimeConnection.objects.filter(pk=connection.pk).record_message()

    connection.refresh_from_db()
    assert connection.connected_at == established
    assert connection.last_message_at is not None
    assert connection.last_message_at > established


def test_an_error_records_its_bounded_message_and_counts_up() -> None:
    """Consecutive failures accumulate so an operator can see a flapping connection."""
    connection = _connection(error_count=2)

    RealTimeConnection.objects.filter(pk=connection.pk).mark_error("sse subscription failed")

    connection.refresh_from_db()
    assert connection.status == "error"
    assert connection.error_message == "sse subscription failed"
    assert connection.error_count == 3
    assert connection.last_error_at is not None


def test_stopping_and_disconnecting_record_when_the_stream_ended() -> None:
    """Both terminal states timestamp the disconnection an operator sees."""
    stopped = _connection(disconnected_at=None)
    disconnected = _connection(disconnected_at=None)

    RealTimeConnection.objects.filter(pk=stopped.pk).mark_stopped()
    RealTimeConnection.objects.filter(pk=disconnected.pk).mark_disconnected()

    stopped.refresh_from_db()
    disconnected.refresh_from_db()
    assert stopped.status == "stopped"
    assert stopped.disconnected_at is not None
    assert disconnected.status == "disconnected"
    assert disconnected.disconnected_at is not None


def test_resetting_errors_leaves_the_connection_state_alone() -> None:
    """Clearing a stale error count is not a claim that the connection is back."""
    connection = _connection(status="error")

    RealTimeConnection.objects.filter(pk=connection.pk).reset_errors()

    connection.refresh_from_db()
    assert connection.status == "error"
    assert connection.error_count == 0
    assert connection.error_message == ""


def test_marking_a_row_connecting_does_not_clear_its_error_history() -> None:
    """A reconnect attempt keeps the failure context until it actually succeeds."""
    connection = _connection(error_count=3)

    RealTimeConnection.objects.filter(pk=connection.pk).mark_connecting()

    connection.refresh_from_db()
    assert connection.status == "connecting"
    assert connection.error_count == 3


def test_the_elapsed_displays_report_nothing_without_a_session() -> None:
    """The admin and the status command show a dash rather than inventing a duration."""
    connection = _connection(status="disconnected", connected_at=None, last_message_at=None)

    assert connection.connected_duration is None
    assert connection.time_since_last_message is None


def test_the_elapsed_displays_measure_from_the_recorded_moments() -> None:
    """A live connection reports how long it has been up and how stale its last update is."""
    established = timezone.now() - timedelta(minutes=3)
    connection = _connection(
        status="connected",
        connected_at=established,
        last_message_at=timezone.now() - timedelta(seconds=30),
    )

    assert connection.connected_duration is not None
    assert connection.connected_duration > timedelta(minutes=2)
    assert connection.time_since_last_message is not None
    assert connection.time_since_last_message > timedelta(seconds=20)


def test_a_connection_that_is_not_live_reports_no_duration() -> None:
    """A stopped row keeps its `connected_at` but is no longer accumulating uptime."""
    connection = _connection(status="stopped", connected_at=timezone.now() - timedelta(hours=1))

    assert connection.connected_duration is None
