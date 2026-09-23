"""The demo deployment must not let its shared account change its own password.

`example_project/urls.py` exposes Django's admin and auth URLs, both of which offer a
password change. The demo signs every visitor in as one shared read-only account, so a
visitor could otherwise lock everyone out until the next redeploy.
"""

from __future__ import annotations

import importlib

import pytest


def _url_patterns(monkeypatch: pytest.MonkeyPatch, *, demo_mode: str) -> list[str]:
    """Reimport the URLconf under a given demo-mode setting and list its routes."""
    monkeypatch.setenv("MICBOARD_DEMO_MODE", demo_mode)
    module = importlib.reload(importlib.import_module("example_project.urls"))
    return [str(pattern.pattern) for pattern in module.urlpatterns]


def test_password_change_is_blocked_in_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both password-change entry points are overridden ahead of the real includes."""
    patterns = _url_patterns(monkeypatch, demo_mode="true")

    assert patterns[0] == "admin/password_change/"
    assert patterns[1] == "accounts/password_change/"


def test_password_change_is_available_outside_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal development or host deployment keeps Django's own behaviour."""
    patterns = _url_patterns(monkeypatch, demo_mode="false")

    assert "admin/password_change/" not in patterns
    assert patterns[0] == "admin/"
