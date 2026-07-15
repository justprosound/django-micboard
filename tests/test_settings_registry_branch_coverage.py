"""Branch contracts for the settings registry cache and scope resolver."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings import registry as registry_module
from micboard.services.settings.registry import SettingsRegistry


def test_get_uses_explicit_default_and_caches_it(monkeypatch) -> None:
    monkeypatch.setattr(SettingsRegistry, "_build_cache_key", Mock(return_value="cache-key"))
    monkeypatch.setattr(registry_module.cache, "get", Mock(return_value=None))
    cache_set = Mock()
    monkeypatch.setattr(registry_module.cache, "set", cache_set)
    monkeypatch.setattr(SettingsRegistry, "_resolve_scoped_value", Mock(return_value=None))

    assert SettingsRegistry.get("missing", "fallback", include_definition_default=False) == (
        "fallback"
    )
    cache_set.assert_called_once_with("cache-key", "fallback", SettingsRegistry.CACHE_TTL)


def test_invalidate_all_definitions_rotates_versions_and_clears_local_cache(monkeypatch) -> None:
    cache_set = Mock()
    monkeypatch.setattr(registry_module.cache, "set", cache_set)
    monkeypatch.setattr(
        registry_module.secrets, "token_hex", Mock(side_effect=["definition", "all"])
    )
    SettingsRegistry._setting_definitions_cache = {"key": ("version", object())}

    SettingsRegistry.invalidate_definition()

    assert SettingsRegistry._setting_definitions_cache == {}
    assert cache_set.call_args_list[0].args == (
        SettingsRegistry._GLOBAL_DEFINITION_VERSION_CACHE_KEY,
        "definition",
    )
    assert cache_set.call_args_list[1].args == (
        SettingsRegistry._GLOBAL_VERSION_CACHE_KEY,
        "all",
    )


@pytest.mark.parametrize(
    "definition",
    [
        SimpleNamespace(scope=SettingDefinition.SCOPE_ORGANIZATION),
        SimpleNamespace(scope=SettingDefinition.SCOPE_SITE),
        SimpleNamespace(scope="unsupported"),
    ],
)
def test_resolve_scoped_value_rejects_missing_or_unknown_scope(monkeypatch, definition) -> None:
    monkeypatch.setattr(SettingsRegistry, "_get_definition", Mock(return_value=definition))
    get_setting = Mock()
    monkeypatch.setattr(Setting.objects, "get", get_setting)

    assert SettingsRegistry._resolve_scoped_value("key", None, None, None) is None
    get_setting.assert_not_called()


def test_resolve_scoped_value_returns_none_when_row_is_absent(monkeypatch) -> None:
    definition = SimpleNamespace(scope=SettingDefinition.SCOPE_GLOBAL)
    monkeypatch.setattr(SettingsRegistry, "_get_definition", Mock(return_value=definition))
    monkeypatch.setattr(
        Setting.objects,
        "get",
        Mock(side_effect=Setting.DoesNotExist),
    )
    assert SettingsRegistry._resolve_scoped_value("key", None, None, None) is None


def test_resolve_scoped_value_uses_site_identifier(monkeypatch) -> None:
    definition = SimpleNamespace(scope=SettingDefinition.SCOPE_SITE)
    setting = SimpleNamespace(get_parsed_value=Mock(return_value=42))
    monkeypatch.setattr(SettingsRegistry, "_get_definition", Mock(return_value=definition))
    get_setting = Mock(return_value=setting)
    monkeypatch.setattr(Setting.objects, "get", get_setting)

    assert (
        SettingsRegistry._resolve_scoped_value("site_value", None, SimpleNamespace(pk=7), None)
        == 42
    )
    assert get_setting.call_args.kwargs["site_id"] == 7
