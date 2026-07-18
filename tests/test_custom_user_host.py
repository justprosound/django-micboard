"""Regression coverage for hosts that replace Django's default user model."""

from __future__ import annotations

import os
import subprocess
import sys


def test_django_check_passes_with_custom_user_model() -> None:
    """Micboard model relations must resolve to the host's swappable user."""
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.custom_user_settings"}
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "import django; "
                "django.setup(); "
                "from django.core.management import call_command; "
                "call_command('check')"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
