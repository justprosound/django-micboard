from __future__ import annotations

import os

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.urls import include, path

# The public demo signs everyone in as one shared read-only account. Django exposes password
# changes through both the admin and the auth views, so a visitor could otherwise change that
# shared password and lock everyone else out until the next redeploy.
DEMO_MODE = os.environ.get("MICBOARD_DEMO_MODE", "False").lower() == "true"


def _password_change_disabled(request: HttpRequest) -> HttpResponse:
    """Refuse password changes for the shared demo account."""
    raise PermissionDenied("Password changes are disabled on the demonstration deployment.")


urlpatterns = []

if DEMO_MODE:
    # Registered ahead of the includes below so these paths win.
    urlpatterns += [
        path("admin/password_change/", _password_change_disabled),
        path("accounts/password_change/", _password_change_disabled),
    ]

urlpatterns += [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("micboard.urls")),
]
