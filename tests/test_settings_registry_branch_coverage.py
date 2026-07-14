"""Branch contracts for the settings registry cache and scope resolver."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.models.settings import Setting, SettingDefinition
from micboard.services.shared import settings_registry as registry_module
from micboard.services.shared.settings_registry import SettingsRegistry


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


def test_set_rejects_mixed_scope(monkeypatch) -> None:
    definition = SimpleNamespace(scope=SettingDefinition.SCOPE_GLOBAL)
    monkeypatch.setattr(
        SettingDefinition.objects,
        "get_or_create",
        Mock(return_value=(definition, False)),
    )
    with pytest.raises(ValueError, match="exactly one scope"):
        SettingsRegistry.set(
            "mixed",
            1,
            organization=SimpleNamespace(pk=1),
            site=SimpleNamespace(pk=2),
        )


def test_set_moves_new_definition_to_requested_scope(monkeypatch) -> None:
    definition = SimpleNamespace(
        scope=SettingDefinition.SCOPE_GLOBAL,
        save=Mock(),
        serialize_value=Mock(return_value="7"),
    )
    monkeypatch.setattr(
        SettingDefinition.objects,
        "get_or_create",
        Mock(return_value=(definition, True)),
    )
    monkeypatch.setattr(
        Setting.objects,
        "get_or_create",
        Mock(return_value=(SimpleNamespace(), True)),
    )
    invalidate = Mock()
    monkeypatch.setattr(SettingsRegistry, "invalidate_cache", invalidate)

    SettingsRegistry.set("organization_limit", 7, organization=SimpleNamespace(pk=4))

    assert definition.scope == SettingDefinition.SCOPE_ORGANIZATION
    definition.save.assert_called_once_with(update_fields=["scope"])
    assert Setting.objects.get_or_create.call_args.kwargs["organization_id"] == 4
    invalidate.assert_called_once_with("organization_limit")


def test_set_rejects_existing_definition_scope_mismatch(monkeypatch) -> None:
    definition = SimpleNamespace(scope=SettingDefinition.SCOPE_SITE)
    monkeypatch.setattr(
        SettingDefinition.objects,
        "get_or_create",
        Mock(return_value=(definition, False)),
    )
    with pytest.raises(ValueError, match="requires 'site' scope"):
        SettingsRegistry.set("site_setting", 1, manufacturer=SimpleNamespace(pk=8))


def test_set_updates_existing_value(monkeypatch) -> None:
    definition = SimpleNamespace(
        scope=SettingDefinition.SCOPE_GLOBAL,
        serialize_value=Mock(return_value="2"),
    )
    setting = SimpleNamespace(set_value=Mock(), save=Mock())
    monkeypatch.setattr(
        SettingDefinition.objects,
        "get_or_create",
        Mock(return_value=(definition, False)),
    )
    monkeypatch.setattr(
        Setting.objects,
        "get_or_create",
        Mock(return_value=(setting, False)),
    )
    monkeypatch.setattr(SettingsRegistry, "invalidate_cache", Mock())

    SettingsRegistry.set("global_setting", 2)

    setting.set_value.assert_called_once_with(2)
    setting.save.assert_called_once_with()


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
