"""Django system checks for django-micboard."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error
from django.core.checks import Warning as CheckWarning


def check_micboard_configuration(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Django system check for Micboard configuration."""
    errors: list[CheckMessage] = []
    if not settings.DEBUG:
        for alias, database in settings.DATABASES.items():
            engine = str(database.get("ENGINE", ""))
            if engine != "django.db.backends.postgresql":
                errors.append(
                    Error(
                        f"Database alias '{alias}' uses an unsupported production backend.",
                        hint=(
                            "Use PostgreSQL via django.db.backends.postgresql. SQLite is "
                            "supported only for local development and tests."
                        ),
                        id="micboard.E001",
                    )
                )
    return errors


def check_realtime_delivery(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Report a WebSocket delivery mode a deployment has only half wired.

    Micboard delivers every live browser surface by short-polling over ordinary HTTP, and
    offers WebSocket push as an opt-in second delivery mode. Push needs two things the app
    itself cannot supply: an ASGI application that routes the protocol, and a channel layer
    to carry broadcasts between processes. Both fail silently when missing — a WSGI server
    never completes a handshake, and a missing layer drops every broadcast at debug level —
    so a deployment can believe it is pushing while every client is really still polling.

    Args:
        app_configs: Unused; present for the Django system check signature.
        **kwargs: Unused; present for the Django system check signature.

    Returns:
        One warning per missing half, or an empty list for a poll-only deployment.
    """
    if "channels" not in settings.INSTALLED_APPS:
        # Polling is the default delivery mode and needs no configuration at all.
        return []

    messages: list[CheckMessage] = []
    if not getattr(settings, "ASGI_APPLICATION", None):
        messages.append(
            CheckWarning(
                "Channels is installed but no ASGI_APPLICATION routes the WebSocket "
                "protocol, so Micboard's WebSocket delivery accepts no connections.",
                hint=(
                    "Point ASGI_APPLICATION at a ProtocolTypeRouter that includes "
                    "micboard.websockets.routing.websocket_urlpatterns, and serve the "
                    "project with an ASGI server. Browser surfaces keep polling over HTTP "
                    "until you do."
                ),
                id="micboard.W002",
            )
        )
    if not getattr(settings, "CHANNEL_LAYERS", None):
        messages.append(
            CheckWarning(
                "Channels is installed but no CHANNEL_LAYERS backend is configured, so "
                "every Micboard realtime broadcast is discarded before delivery.",
                hint=(
                    "Configure a CHANNEL_LAYERS default backend, such as "
                    "channels_redis.core.RedisChannelLayer for multi-process deployments."
                ),
                id="micboard.W003",
            )
        )
    return messages
