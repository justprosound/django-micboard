"""Isolation fixtures for sync service tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from micboard.services.manufacturer.plugin_registry import PluginRegistry


@pytest.fixture(autouse=True)
def isolate_hardware_factory_side_effects(
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep model factories local while preserving their database behavior."""
    settings.TESTING = True
    monkeypatch.setattr(PluginRegistry, "get_plugin", lambda *_args, **_kwargs: None)
    yield
