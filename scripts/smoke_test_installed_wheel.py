#!/usr/bin/env python3
# ruff: noqa: S106, T201
"""Smoke-test django-micboard from an installed wheel, outside the source tree."""

from __future__ import annotations

import importlib
from importlib.resources import files
from pathlib import Path

from django.conf import settings


def main() -> int:
    """Start Django and import representative modules from the installed wheel."""
    settings.configure(
        DEBUG=True,
        SECRET_KEY="wheel-smoke",
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.messages",
            "django.contrib.sessions",
            "django.contrib.sites",
            "micboard",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                    ]
                },
            }
        ],
        SITE_ID=1,
    )

    import django

    django.setup()

    from django.contrib import admin
    from django.contrib.auth.models import User
    from django.core.management import call_command

    import micboard
    import micboard.integrations.shure.client
    import micboard.integrations.shure.exceptions
    import micboard.integrations.shure.transformers
    import micboard.management.commands.poll_devices
    import micboard.models.hardware.wireless_chassis
    import micboard.services.sync.discovery_service
    from micboard.admin import users as micboard_user_admin

    if (
        micboard.integrations.shure.client.ShureAPIError
        is not micboard.integrations.shure.exceptions.ShureAPIError
    ):
        raise RuntimeError("Shure client does not use the canonical integration exception")
    if not admin.site.is_registered(User):
        raise RuntimeError("standalone admin did not register User")
    admin.site.unregister(User)
    importlib.reload(micboard_user_admin)
    if admin.site.is_registered(User):
        raise RuntimeError("Micboard registered User despite the host omitting it")

    call_command("check")

    project_root = Path(__file__).resolve().parent.parent
    installed_path = Path(micboard.__file__).resolve()
    if installed_path.is_relative_to(project_root):
        raise RuntimeError(f"import resolved to source checkout: {installed_path}")

    package_files = files("micboard")
    required_resources = (
        "fixtures/device_specifications.yaml",
        "static/micboard/logo.png",
        "templates/micboard/base.html",
    )
    missing = [
        resource
        for resource in required_resources
        if not package_files.joinpath(resource).is_file()
    ]
    if missing:
        raise RuntimeError(f"installed wheel is missing resources: {', '.join(missing)}")

    print(f"OK installed wheel: {installed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
