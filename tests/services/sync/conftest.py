"""Isolation fixtures for sync service tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from micboard.services.common.base import plugin as plugin_module


@pytest.fixture(autouse=True)
def isolate_hardware_factory_side_effects(
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep model factories local while preserving their database behavior."""
    settings.TESTING = True
    monkeypatch.setattr(
        plugin_module,
        "build_manufacturer_plugin",
        lambda _manufacturer: (_ for _ in ()).throw(ModuleNotFoundError("no integration")),
    )
    yield
