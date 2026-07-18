"""Behavioral coverage for email, notification signals, and connection state."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call

from django.utils import timezone

from micboard.services.notification import email as email_module
from micboard.services.notification.email_notification import EmailService
from micboard.services.realtime import connection_service


def test_email_alert_delivery_covers_defaults_success_rejection_and_exception(
    monkeypatch,
    caplog,
) -> None:
    connection = Mock()
    monkeypatch.setattr(email_module, "get_connection", Mock(return_value=connection))
    service = EmailService()
    assert service.connection is connection
    alert = SimpleNamespace(id=7, get_alert_type_display=Mock(return_value="Low battery"))
    service._get_default_recipients = Mock(return_value=[])
    assert not service.send_alert_notification(alert)

    service._get_default_recipients.return_value = ["ops@example.test"]
    service._get_from_email = Mock(return_value="micboard@example.test")
    monkeypatch.setattr(
        email_module, "render_to_string", Mock(side_effect=["<p>alert</p>", "alert"])
    )
    message = Mock(send=Mock(return_value=1))
    message_factory = Mock(return_value=message)
    monkeypatch.setattr(email_module, "EmailMessage", message_factory)
    assert service.send_alert_notification(alert)
    assert message.content_subtype == "html"
    assert message.body == "<p>alert</p>"

    email_module.render_to_string.side_effect = None
    email_module.render_to_string.return_value = "rendered"
    message.send.return_value = 0
    assert not service.send_alert_notification(alert, ["other@example.test"])
    message.send.side_effect = RuntimeError("smtp://operator:secret@example.test")
    assert not service.send_alert_notification(alert, ["other@example.test"])
    assert "operator:secret" not in caplog.text
    assert "error details redacted" in caplog.text


def test_email_settings_helpers_validate_recipient_shapes(monkeypatch) -> None:
    service = EmailService()
    config = Mock()
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings.get_config_dict",
        config,
    )
    config.side_effect = [
        {"EMAIL_RECIPIENTS": "one@example.test"},
        {"EMAIL_RECIPIENTS": ("invalid",)},
        {"EMAIL_RECIPIENTS": ["two@example.test"]},
        {"EMAIL_FROM": "sender@example.test"},
        {},
    ]
    assert service._get_default_recipients() == ["one@example.test"]
    assert service._get_default_recipients() == []
    assert service._get_default_recipients() == ["two@example.test"]
    assert service._get_from_email() == "sender@example.test"
    assert service._get_from_email()


def _connection(**overrides):
    values = {
        "status": "disconnected",
        "connected_at": None,
        "disconnected_at": None,
        "last_message_at": None,
        "last_error_at": None,
        "error_count": 0,
        "error_message": "",
        "reconnect_attempts": 0,
        "max_reconnect_attempts": 3,
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_connection_state_helpers_cover_every_transition(monkeypatch) -> None:
    first = timezone.now()
    clock = iter(first + timedelta(seconds=index) for index in range(20))
    monkeypatch.setattr(connection_service.timezone, "now", lambda: next(clock))
    conn = _connection(error_count=2, reconnect_attempts=2)

    connection_service.mark_connected(conn)
    assert conn.status == "connected"
    assert conn.error_count == 0
    assert conn.reconnect_attempts == 0
    connection_service.mark_error(conn, "failed")
    assert conn.status == "error"
    connection_service.mark_connecting(conn)
    assert conn.status == "connecting"
    connection_service.mark_stopped(conn)
    assert conn.status == "stopped"

    conn.last_message_at = None
    assert connection_service.time_since_last_message(conn) is None
    conn.last_message_at = first
    assert connection_service.time_since_last_message(conn) > timedelta(0)
    conn.connected_at = None
    assert connection_service.connection_duration(conn) is None
    conn.connected_at = first
    conn.status = "connected"
    assert connection_service.connection_duration(conn) > timedelta(0)

    conn.status = "connecting"
    connection_service.received_message(conn)
    assert conn.status == "connected"
    connection_service.received_message(conn)
    assert conn.save.call_args == call(update_fields=["last_message_at"])
