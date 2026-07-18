"""Django system checks for django-micboard."""

from __future__ import annotations
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error


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
