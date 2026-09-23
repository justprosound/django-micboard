"""Deployment contract coverage for Micboard system checks."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings

from micboard.checks import check_micboard_configuration, check_realtime_delivery


@override_settings(
    DEBUG=False,
)
def test_production_check_rejects_non_postgresql_database(monkeypatch) -> None:
    """Cross-model IP ownership requires PostgreSQL transaction locks in production."""
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.mysql", "NAME": "micboard"}},
    )
    errors = check_micboard_configuration(None)

    assert [error.id for error in errors] == ["micboard.E001"]
    assert "PostgreSQL" in errors[0].hint


@override_settings(
    DEBUG=False,
)
def test_production_check_accepts_postgresql_database(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "micboard"}},
    )
    assert check_micboard_configuration(None) == []


@override_settings(
    DEBUG=True,
)
def test_development_check_allows_sqlite(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    )
    assert check_micboard_configuration(None) == []


@override_settings(INSTALLED_APPS=["micboard"])
def test_a_poll_only_deployment_is_reported_as_complete() -> None:
    """Polling is Micboard's default delivery mode, so it needs no configuration.

    Every live browser surface refreshes over ordinary HTTP. A deployment that never
    installs Channels has not left anything half-wired and must not be warned about it.
    """
    assert check_realtime_delivery(None) == []


@override_settings(
    INSTALLED_APPS=["micboard", "channels"],
    ASGI_APPLICATION=None,
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
def test_websocket_delivery_without_an_asgi_application_is_reported() -> None:
    """Channels under WSGI accepts no WebSocket at all, and says nothing about it.

    The failure is silent from the server's side: the consumer is importable and the
    routing module resolves, but no handshake ever reaches either.
    """
    ids = [message.id for message in check_realtime_delivery(None)]

    assert ids == ["micboard.W002"]


@override_settings(
    INSTALLED_APPS=["micboard", "channels"],
    ASGI_APPLICATION="example_project.asgi.application",
    CHANNEL_LAYERS={},
)
def test_websocket_delivery_without_a_channel_layer_is_reported() -> None:
    """Without a layer every broadcast is dropped at debug level and never delivered."""
    ids = [message.id for message in check_realtime_delivery(None)]

    assert ids == ["micboard.W003"]


@override_settings(
    INSTALLED_APPS=["micboard", "channels"],
    ASGI_APPLICATION="example_project.asgi.application",
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
def test_a_fully_wired_push_deployment_is_reported_as_complete() -> None:
    """Both halves present means push is a delivery mode this deployment can serve."""
    assert check_realtime_delivery(None) == []
