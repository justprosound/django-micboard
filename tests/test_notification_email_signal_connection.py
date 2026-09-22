"""Behavioral coverage for email, notification signals, and connection state."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from micboard.services.notification import email_notification as email_module
from micboard.services.notification.email_notification import EmailService


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
