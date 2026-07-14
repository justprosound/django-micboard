"""Isolation fixtures for sync service tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolate_hardware_factory_side_effects(settings: Any) -> Iterator[None]:
    """Keep model factories local while preserving their database behavior."""
    settings.TESTING = True
    with patch(
        "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
        return_value=None,
    ):
        yield
