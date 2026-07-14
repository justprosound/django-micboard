"""Coverage for settings, gap-analysis, and user admin behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django import forms
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

import pytest

from micboard.admin import (
    configuration,
    users,
)
from micboard.admin import (
    settings as settings_admin,
)
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.settings.registry import Setting, SettingDefinition

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _request() -> Any:
    request = RequestFactory().get("/admin/")
    request.user = SimpleNamespace(pk=4, is_authenticated=True, is_superuser=True)
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_safe_fieldset_helpers_replace_or_remove_raw_values() -> None:
    fieldsets = (("Data", {"fields": ("name", "secret"), "classes": ("collapse",)}),)
    replaced = configuration.replace_field(
        fieldsets, raw_field="secret", display_field="secret_masked"
    )
    assert replaced[0][1]["fields"] == ("name", "secret_masked")
    assert replaced[0][1]["classes"] == ("collapse",)
    removed = settings_admin._without_raw_field(fieldsets, raw_field="secret")
    assert removed[0][1]["fields"] == ("name",)


def test_setting_definition_admin_displays_persistence_and_invalidation() -> None:
    model_admin = _admin(settings_admin.SettingDefinitionAdmin, SettingDefinition)
    obj = SimpleNamespace(
        pk=2,
        key="new-key",
        label="Label",
        scope="global",
        get_scope_display=lambda: "Global",
        get_setting_type_display=lambda: "Text",
        required=True,
        is_active=True,
        default_value="value",
        parse_value=Mock(return_value="parsed"),
    )
    assert "Global" in model_admin.scope_badge(obj)
    obj.scope = "custom"
    assert "Global" in model_admin.scope_badge(obj)
    assert model_admin.type_badge(obj) == "Text"
    assert model_admin.required_badge(obj) is True
    assert model_admin.is_active_badge(obj) is True
    with (
        patch.object(
            settings_admin.settings_presentation,
            "is_sensitive_definition",
            return_value=False,
        ),
        patch.object(
            settings_admin.settings_presentation, "format_value", return_value="formatted"
        ),
    ):
        assert model_admin.default_value_display(obj) == "formatted"
    obj.parse_value.side_effect = ValueError("bad")
    with patch.object(
        settings_admin.settings_presentation, "is_sensitive_definition", return_value=False
    ):
        assert "Parse Error" in model_admin.default_value_display(obj)
    with (
        patch.object(
            settings_admin.settings_presentation,
            "is_sensitive_definition",
            return_value=True,
        ),
        patch.object(settings_admin.settings_presentation, "format_value", return_value="••••"),
    ):
        assert model_admin.default_value_display(obj) == "••••"

    previous = MagicMock()
    previous.values_list.return_value.first.return_value = "old-key"
    with (
        patch.object(settings_admin.SettingDefinition.objects, "filter", return_value=previous),
        patch.object(MicboardModelAdmin, "save_model"),
        patch.object(settings_admin.SettingsRegistry, "invalidate_definition") as invalidate,
    ):
        model_admin.save_model(_request(), obj, MagicMock(), change=True)
    assert {item.args[0] for item in invalidate.call_args_list} == {"old-key", "new-key"}

    queryset = MagicMock()
    queryset.values_list.return_value = ["one", "two"]
    with (
        patch.object(MicboardModelAdmin, "delete_model"),
        patch.object(MicboardModelAdmin, "delete_queryset"),
        patch.object(settings_admin.SettingsRegistry, "invalidate_definition") as invalidate,
    ):
        model_admin.delete_model(_request(), obj)
        model_admin.delete_queryset(_request(), queryset)
    assert {item.args[0] for item in invalidate.call_args_list} == {"new-key", "one", "two"}
    assert model_admin.has_import_permission(_request()) is False
    assert model_admin.has_export_permission(_request()) is False


def test_setting_admin_query_form_displays_and_scope_paths() -> None:
    model_admin = _admin(settings_admin.SettingAdmin, Setting)
    request = _request()
    queryset = MagicMock()
    scope = object()
    management_filter = object()
    with (
        patch.object(admin.ModelAdmin, "get_queryset", return_value=queryset),
        patch.object(settings_admin.settings_visibility, "for_user", return_value=scope),
        patch.object(
            settings_admin.settings_visibility,
            "build_management_filter",
            return_value=management_filter,
        ),
    ):
        result = model_admin.get_queryset(request)
    assert result is queryset.filter.return_value.select_related.return_value
    queryset.filter.assert_called_once_with(management_filter)

    class ParentForm(forms.ModelForm):
        received_user: Any = None

        class Meta:
            model = Setting
            fields = ()

        def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.received_user = user

    with patch.object(MicboardModelAdmin, "get_form", return_value=ParentForm):
        scoped_form = model_admin.get_form(request)
    assert scoped_form().received_user is request.user

    definition = SimpleNamespace(
        key="example", label="Example", get_setting_type_display=lambda: "Text"
    )
    obj = SimpleNamespace(
        definition=definition,
        value="x" * 60,
        organization_id=3,
        site=None,
        manufacturer_id=None,
        get_parsed_value=Mock(return_value={"x": 1}),
    )
    assert model_admin.setting_key(obj) == "example (Example)"
    with (
        patch.object(settings_admin.settings_presentation, "format_value", return_value="x" * 60),
        patch.object(
            settings_admin.settings_presentation,
            "is_sensitive_definition",
            return_value=False,
        ),
    ):
        assert model_admin.value_display(obj).endswith("...")
        assert "<code>" in model_admin.parsed_value_display(obj)
    assert model_admin.scope_display(obj) == "Org ID: 3"
    obj.organization_id = None
    obj.site = SimpleNamespace(name="Site")
    assert model_admin.scope_display(obj) == "Site: Site"
    obj.site = None
    obj.manufacturer_id = 5
    assert model_admin.scope_display(obj) == "Mfg ID: 5"
    obj.manufacturer_id = None
    assert model_admin.scope_display(obj) == "Global"
    assert model_admin.definition_type(obj) == "Text"
    with (
        patch.object(
            settings_admin.settings_presentation,
            "is_sensitive_definition",
            return_value=True,
        ),
        patch.object(settings_admin.settings_presentation, "format_value", return_value="••••"),
    ):
        assert model_admin.value_display(obj) == "••••"
        assert model_admin.parsed_value_display(obj) == "••••"
    obj.get_parsed_value.side_effect = ValueError("bad")
    with patch.object(
        settings_admin.settings_presentation, "is_sensitive_definition", return_value=False
    ):
        assert "Parse Error" in model_admin.parsed_value_display(obj)


def test_setting_admin_save_authorizes_reports_and_invalidates() -> None:
    model_admin = _admin(settings_admin.SettingAdmin, Setting)
    request = _request()
    definition = SimpleNamespace(key="new", label="Example")
    obj = SimpleNamespace(
        pk=2,
        definition=definition,
        organization_id=None,
        site_id=None,
        manufacturer_id=None,
    )
    previous = MagicMock()
    previous.values_list.return_value.first.return_value = "old"
    with (
        patch.object(settings_admin.Setting.objects, "filter", return_value=previous),
        patch.object(settings_admin.settings_visibility, "for_user", return_value="scope"),
        patch.object(settings_admin.settings_visibility, "can_manage_scope", return_value=True),
        patch.object(MicboardModelAdmin, "save_model"),
        patch.object(settings_admin.messages, "success") as success,
        patch.object(settings_admin.SettingsRegistry, "invalidate_cache") as invalidate,
    ):
        model_admin.save_model(request, obj, MagicMock(), change=True)
        obj.pk = None
        model_admin.save_model(request, obj, MagicMock(), change=False)
    assert "updated" in success.call_args_list[0].args[1]
    assert "created" in success.call_args_list[1].args[1]
    assert {item.args[0] for item in invalidate.call_args_list} == {"old", "new"}

    with (
        patch.object(settings_admin.settings_visibility, "for_user", return_value="scope"),
        patch.object(settings_admin.settings_visibility, "can_manage_scope", return_value=False),
        pytest.raises(PermissionDenied),
    ):
        model_admin.save_model(request, obj, MagicMock(), change=False)

    queryset = MagicMock()
    queryset.values_list.return_value = ["one", "two"]
    with (
        patch.object(MicboardModelAdmin, "delete_model"),
        patch.object(MicboardModelAdmin, "delete_queryset"),
        patch.object(settings_admin.SettingsRegistry, "invalidate_cache") as invalidate,
    ):
        model_admin.delete_model(request, obj)
        model_admin.delete_queryset(request, queryset)
    assert {item.args[0] for item in invalidate.call_args_list} == {"new", "one", "two"}
    assert model_admin.has_import_permission(request) is False
    assert model_admin.has_export_permission(request) is False


def test_setting_admin_view_only_fieldsets_hide_raw_values() -> None:
    request = _request()
    definition_admin = _admin(settings_admin.SettingDefinitionAdmin, SettingDefinition)
    value_admin = _admin(settings_admin.SettingAdmin, Setting)
    with patch.object(definition_admin, "has_change_permission", return_value=False):
        fieldsets = definition_admin.get_fieldsets(request, SimpleNamespace())
    assert all("default_value" not in options["fields"] for _title, options in fieldsets)
    with patch.object(value_admin, "has_change_permission", return_value=False):
        fieldsets = value_admin.get_fieldsets(request, SimpleNamespace())
    assert all("value" not in options["fields"] for _title, options in fieldsets)
    with patch.object(MicboardModelAdmin, "get_fieldsets", return_value=[("base", {})]):
        assert definition_admin.get_fieldsets(request, None) == [("base", {})]
        assert value_admin.get_fieldsets(request, None) == [("base", {})]


def test_user_admin_helpers_cover_profile_and_host_registration_policy() -> None:
    model_admin = users.UserProfileAdmin(users.UserProfile, AdminSite())
    assert model_admin.list_select_related == ("user",)
    site = MagicMock()
    site.is_registered.side_effect = [False, True]
    users.register_user_profile_admin(site)
    users.register_user_profile_admin(site)
    site.unregister.assert_not_called()
    site.register.assert_called_once_with(users.UserProfile, users.UserProfileAdmin)
