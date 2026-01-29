"""Email notification utilities for django-micboard.

Provides email sending functionality for alerts and system notifications
using Django's built-in email system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models import Alert

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications.

    Uses Django's email backend for reliable delivery.
    """

    def __init__(self):
        """Prepare an email backend connection for sending messages."""
        self.connection = get_connection()

    def send_alert_notification(self, alert: Alert, recipients: list[str] | None = None) -> bool:
        """Send email notification for an alert.

        Args:
            alert: Alert instance
            recipients: List of email addresses, or None to use default

        Returns:
            bool: True if email was sent successfully
        """
        if not recipients:
            recipients = self._get_default_recipients()

        if not recipients:
            logger.warning("No email recipients configured for alerts")
            return False

        try:
            subject = f"Micboard Alert: {alert.get_alert_type_display()}"
            context = {
                "alert": alert,
                "site_url": getattr(settings, "SITE_URL", "http://localhost:8000"),
                "timestamp": timezone.now(),
            }

            # Render HTML email
            html_message = render_to_string("micboard/emails/alert_notification.html", context)
            # Render plain text fallback
            text_message = render_to_string("micboard/emails/alert_notification.txt", context)

            email = EmailMessage(
                subject=subject,
                body=text_message,
                from_email=self._get_from_email(),
                to=recipients,
                connection=self.connection,
            )
            # Set HTML alternative
            email.content_subtype = "html"
            email.body = html_message

            sent = email.send()
            if sent:
                logger.info(
                    f"Alert notification sent to {len(recipients)} recipients for alert {alert.id}"
                )
                return True
            else:
                logger.error(f"Failed to send alert notification for alert {alert.id}")
                return False

        except Exception as e:
            logger.exception(f"Error sending alert notification for alert {alert.id}: {e}")
            return False

    def send_system_notification(
        self, subject: str, message: str, recipients: list[str] | None = None
    ) -> bool:
        """Send system notification email.

        Args:
            subject: Email subject
            message: Email message body
            recipients: List of email addresses, or None to use default

        Returns:
            bool: True if email was sent successfully
        """
        if not recipients:
            recipients = self._get_default_recipients()

        if not recipients:
            logger.warning("No email recipients configured for system notifications")
            return False

        try:
            email = EmailMessage(
                subject=f"Micboard System: {subject}",
                body=message,
                from_email=self._get_from_email(),
                to=recipients,
                connection=self.connection,
            )

            sent = email.send()
            if sent:
                logger.info(f"System notification sent to {len(recipients)} recipients")
                return True
            else:
                logger.error("Failed to send system notification")
                return False

        except Exception as e:
            logger.exception(f"Error sending system notification: {e}")
            return False

    def _get_default_recipients(self) -> list[str]:
        """Get default email recipients from settings."""
        from micboard.apps import MicboardConfig

        config = MicboardConfig.get_config()
        recipients = config.get("EMAIL_RECIPIENTS", [])

        # Ensure it's a list
        if isinstance(recipients, str):
            recipients = [recipients]
        elif not isinstance(recipients, list):
            recipients = []

        return cast(list[str], recipients)

    def _get_from_email(self) -> str:
        """Get from email address from settings."""
        from micboard.apps import MicboardConfig

        config = MicboardConfig.get_config()
        return str(
            config.get("EMAIL_FROM", getattr(settings, "DEFAULT_FROM_EMAIL", "micboard@localhost"))
        )


# Global email service instance
email_service = EmailService()


def send_alert_email(alert: Alert, recipients: list[str] | None = None) -> bool:
    """Convenience function to send alert email.

    Args:
        alert: Alert instance
        recipients: Optional list of email addresses

    Returns:
        bool: True if email was sent successfully
    """
    return email_service.send_alert_notification(alert, recipients)


def send_system_email(subject: str, message: str, recipients: list[str] | None = None) -> bool:
    """Convenience function to send system email.

    Args:
        subject: Email subject
        message: Email message
        recipients: Optional list of email addresses

    Returns:
        bool: True if email was sent successfully
    """
    return email_service.send_system_notification(subject, message, recipients)
