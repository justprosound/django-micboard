"""Shared isolation for core service tests."""

from __future__ import annotations

from collections.abc import Iterator

from django.conf import LazySettings

import pytest

from micboard.services.manufacturer.plugin_registry import PluginRegistry


@pytest.fixture(autouse=True)
def isolate_hardware_integrations(
    settings: LazySettings,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep model lifecycle hooks from loading plugins or dispatching tasks."""
    settings.TESTING = True
    monkeypatch.setattr(PluginRegistry, "get_plugin", lambda *_args, **_kwargs: None)
    yield
