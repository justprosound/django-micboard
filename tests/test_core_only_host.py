"""Regression coverage for Micboard's optional-app dependency boundary."""

from __future__ import annotations

import os
import subprocess
import sys


def test_core_only_host_has_no_multitenancy_models_or_migration_drift() -> None:
    """Core startup must not register models owned by the optional MSP app."""
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.core_only_settings"}
    script = (
        "import django; "
        "django.setup(); "
        "from django.apps import apps; "
        "assert 'organization' not in apps.all_models['micboard']; "
        "assert 'campus' not in apps.all_models['micboard']; "
        "from django.core.management import call_command; "
        "call_command('check'); "
        "call_command('makemigrations', 'micboard', check=True, dry_run=True, verbosity=0)"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
