"""How a manufacturer plugin is resolved and built.

Every outbound path — polling, discovery, refresh, realtime, the admin — needs a plugin for
a manufacturer. There is one way to get one, it is cached, and it fails the same way for
every caller.
"""

from __future__ import annotations

import pytest

from micboard.integrations.sennheiser.plugin import SennheiserPlugin
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.services.common.base.plugin import (
    ManufacturerPlugin,
    build_manufacturer_plugin,
    clear_plugin_cache,
    get_manufacturer_plugin,
)
from tests.factories.discovery import ManufacturerFactory


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Resolution is cached per process, so each test starts from a cold cache."""
    clear_plugin_cache()


def test_each_shipped_integration_resolves_to_its_plugin() -> None:
    """The two shipped adapters are reachable by manufacturer code."""
    assert get_manufacturer_plugin("shure") is ShurePlugin
    assert get_manufacturer_plugin("sennheiser") is SennheiserPlugin


def test_an_unknown_manufacturer_code_raises() -> None:
    """A missing integration is an error, not a None every caller must branch on."""
    with pytest.raises(ModuleNotFoundError, match="nosuchvendor"):
        get_manufacturer_plugin("nosuchvendor")


def test_resolution_is_cached_across_calls() -> None:
    """Import and subclass scanning happen once per code, not per outbound call."""
    first = get_manufacturer_plugin("shure")

    assert get_manufacturer_plugin("shure") is first


@pytest.mark.django_db
def test_building_a_plugin_binds_it_to_its_manufacturer() -> None:
    """Callers hold a plugin bound to the row they resolved it for."""
    manufacturer = ManufacturerFactory(code="shure")

    plugin = build_manufacturer_plugin(manufacturer)

    assert isinstance(plugin, ManufacturerPlugin)
    assert isinstance(plugin, ShurePlugin)
    assert plugin.manufacturer == manufacturer


@pytest.mark.django_db
def test_building_a_plugin_for_an_unsupported_manufacturer_raises() -> None:
    """A configured manufacturer with no shipped integration fails loudly."""
    manufacturer = ManufacturerFactory(code="nosuchvendor")

    with pytest.raises(ModuleNotFoundError, match="nosuchvendor"):
        build_manufacturer_plugin(manufacturer)


def test_a_missing_vendor_dependency_is_not_reported_as_a_missing_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shipped integration that cannot import its own dependency is a different fault.

    Swallowing it would send an operator looking for an uninstalled integration instead of a
    missing package, the same way a caught `ValueError` once did.
    """
    import importlib

    def fail_inside_plugin(name: str) -> object:
        raise ModuleNotFoundError("No module named 'websockets'", name="websockets")

    monkeypatch.setattr(importlib, "import_module", fail_inside_plugin)

    with pytest.raises(ModuleNotFoundError, match="websockets"):
        get_manufacturer_plugin("shure")
