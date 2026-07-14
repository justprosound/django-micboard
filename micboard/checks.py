"""Django system checks for django-micboard."""

from __future__ import annotations

from django.core.checks import CheckMessage


def check_micboard_configuration(app_configs, **kwargs) -> list[CheckMessage]:
    """Django system check for Micboard configuration."""
    errors: list[CheckMessage] = []
    # Add custom validation logic here if needed
    return errors
