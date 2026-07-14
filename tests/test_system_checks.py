"""Deployment contract coverage for Micboard system checks."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings

from micboard.checks import check_micboard_configuration


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
