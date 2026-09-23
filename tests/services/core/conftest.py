"""Shared isolation for core service tests."""

from __future__ import annotations

from collections.abc import Iterator

from django.conf import LazySettings

import pytest

from micboard.services.common.base import plugin as plugin_module


@pytest.fixture(autouse=True)
def isolate_hardware_integrations(
    settings: LazySettings,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep model lifecycle hooks from loading plugins or dispatching tasks."""
    settings.TESTING = True
    monkeypatch.setattr(
        plugin_module,
        "build_manufacturer_plugin",
        lambda _manufacturer: (_ for _ in ()).throw(ModuleNotFoundError("no integration")),
    )
    yield
