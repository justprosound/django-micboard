"""Focused presentation, scoping, and validation coverage for settings admin forms."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django import forms

import pytest

from micboard.forms.settings_admin import SettingDefinitionForm, SettingValueForm
from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import SettingsVisibilityScope


def test_setting_definition_form_sensitive_init_and_clean_branches() -> None:
    instance = SettingDefinition(
        pk=1,
        key="api_token",
        default_value="stored",
        setting_type=SettingDefinition.TYPE_STRING,
    )
    with patch(
        "micboard.forms.settings_admin.settings_presentation.is_key_sensitive", return_value=True
    ):
        form = SettingDefinitionForm(instance=instance)
    assert isinstance(form.fields["default_value"].widget, forms.PasswordInput)
    assert form.fields["default_value"].required is False

    form.cleaned_data = {
        "key": "api_token",
        "default_value": "",
        "setting_type": SettingDefinition.TYPE_CHOICES,
        "choices_json": None,
    }
    with (
        patch("django.forms.models.BaseModelForm.clean", return_value=form.cleaned_data),
        patch(
            "micboard.forms.settings_admin.settings_presentation.is_key_sensitive",
            return_value=True,
        ),
        patch.object(form, "add_error") as add_error,
    ):
        cleaned = form.clean()
    assert cleaned["default_value"] == "stored"
    add_error.assert_called_once_with("setting_type", "Choices JSON is required for dropdown type")

    bound = SettingDefinitionForm(
        data={"key": "submitted_secret"},
        instance=SettingDefinition(key="public"),
    )
    with patch(
        "micboard.forms.settings_admin.settings_presentation.is_key_sensitive", return_value=False
    ):
        assert bound.fields["default_value"].required is True


def _fake_setting_value(cleaned_data: dict[str, Any], *, saved: bool = False) -> SettingValueForm:
    form = object.__new__(SettingValueForm)
    form.cleaned_data = cleaned_data
    form.visibility_scope = SettingsVisibilityScope()
    form.instance = SimpleNamespace(pk=1 if saved else None, value="stored")
    form.add_error = Mock()
    return form


@pytest.mark.parametrize(
    ("setting_type", "expected"),
    [
        (SettingDefinition.TYPE_BOOLEAN, "true, false"),
        (SettingDefinition.TYPE_INTEGER, "integer"),
        (SettingDefinition.TYPE_CHOICES, "Choose from"),
    ],
)
def test_setting_value_init_describes_selected_definition(setting_type: str, expected: str) -> None:
    definition = SimpleNamespace(
        key="poll_interval",
        setting_type=setting_type,
        choices_json={"one": "One"},
    )
    with (
        patch.object(SettingValueForm, "_scope_target_fields"),
        patch.object(SettingValueForm, "_selected_definition", return_value=definition),
        patch(
            "micboard.forms.settings_admin.settings_presentation.is_key_sensitive",
            return_value=False,
        ),
    ):
        form = SettingValueForm(instance=Setting())
    assert expected in form.fields["value"].help_text


def test_setting_value_init_masks_unknown_definition() -> None:
    with (
        patch.object(SettingValueForm, "_scope_target_fields"),
        patch.object(SettingValueForm, "_selected_definition", return_value=None),
    ):
        form = SettingValueForm(instance=Setting())
    assert isinstance(form.fields["value"].widget, forms.PasswordInput)
    assert form.fields["value"].required is True


def test_selected_definition_uses_instance_or_bound_submission() -> None:
    fake = SimpleNamespace(
        instance=SimpleNamespace(definition_id=None),
        is_bound=False,
        data={},
        add_prefix=lambda name: name,
    )
    assert SettingValueForm._selected_definition(fake) is None
    fake.instance.definition_id = 3
    queryset = MagicMock()
    with patch(
        "micboard.forms.settings_admin.SettingDefinition.objects.filter", return_value=queryset
    ):
        assert SettingValueForm._selected_definition(fake) is queryset.first.return_value
    fake.is_bound = True
    fake.data = {"definition": "4"}
    with patch(
        "micboard.forms.settings_admin.SettingDefinition.objects.filter", return_value=queryset
    ) as filter_definition:
        SettingValueForm._selected_definition(fake)
    filter_definition.assert_called_once_with(pk="4")


@pytest.mark.parametrize("installed", [False, True])
def test_setting_value_scope_fields_build_exact_visible_choices(installed: bool) -> None:
    definition_field = forms.ModelChoiceField(queryset=SettingDefinition.objects.none())
    site_field = forms.ModelChoiceField(queryset=SettingDefinition.objects.none())
    fake = SimpleNamespace(
        fields={"definition": definition_field, "site": site_field},
        visibility_scope=SettingsVisibilityScope(
            organization_ids=frozenset({1}),
            site_ids=frozenset({2}),
            manufacturer_ids=frozenset({3}),
        ),
        instance=SimpleNamespace(definition_id=7),
    )
    definitions = MagicMock()
    organizations = MagicMock()
    sites = MagicMock()
    manufacturers = MagicMock()
    organizations.filter.return_value.values_list.return_value = [(1, "Org")]
    sites.filter.return_value = sites
    manufacturers.filter.return_value.values_list.return_value = [(3, "Vendor")]
    with (
        patch("micboard.forms.settings_admin.apps.is_installed", return_value=installed),
        patch(
            "micboard.forms.settings_admin.SettingDefinition.objects.filter",
            return_value=definitions,
        ),
        patch("micboard.forms.settings_admin.Site.objects.all", return_value=sites),
        patch(
            "micboard.models.discovery.manufacturer.Manufacturer.objects.all",
            return_value=manufacturers,
        ),
        patch(
            "micboard.multitenancy.models.Organization._default_manager.all",
            return_value=organizations,
        ),
    ):
        SettingValueForm._scope_target_fields(fake)

    assert fake.fields["definition"].queryset is definitions.all.return_value
    sites.filter.assert_called_once_with(pk__in=frozenset({2}))
    manufacturers.filter.assert_called_once_with(pk__in=frozenset({3}))
    manufacturer_choices = list(fake.fields["manufacturer_id"].choices)
    assert manufacturer_choices[0][0] == ""
    if installed:
        organizations.filter.assert_called_once_with(pk__in=frozenset({1}))
        assert len(list(fake.fields["organization_id"].choices)) == 2
    else:
        organizations.filter.assert_not_called()


def test_setting_value_clean_preserves_secret_parses_and_authorizes() -> None:
    definition = SimpleNamespace(
        key="shared_secret",
        scope=SettingDefinition.SCOPE_GLOBAL,
        setting_type=SettingDefinition.TYPE_INTEGER,
        parse_value=Mock(),
    )
    cleaned_data = {"definition": definition, "value": "", "organization_id": None}
    form = _fake_setting_value(cleaned_data, saved=True)
    with (
        patch("django.forms.models.BaseModelForm.clean", return_value=cleaned_data),
        patch(
            "micboard.forms.settings_admin.settings_presentation.is_key_sensitive",
            return_value=True,
        ),
        patch(
            "micboard.forms.settings_admin.matches_definition_scope",
            return_value=True,
        ),
        patch(
            "micboard.forms.settings_admin.settings_visibility.can_manage_scope", return_value=True
        ),
    ):
        result = SettingValueForm.clean(form)
    assert result["value"] == "stored"
    definition.parse_value.assert_called_once_with("stored")


def test_setting_value_clean_records_parse_error_and_rejects_scope_mismatch() -> None:
    definition = SimpleNamespace(
        key="poll_interval",
        scope=SettingDefinition.SCOPE_SITE,
        setting_type=SettingDefinition.TYPE_INTEGER,
        parse_value=Mock(side_effect=ValueError("not int")),
    )
    cleaned_data = {"definition": definition, "value": "bad", "site": SimpleNamespace(pk=2)}
    form = _fake_setting_value(cleaned_data)
    with (
        patch("django.forms.models.BaseModelForm.clean", return_value=cleaned_data),
        patch(
            "micboard.forms.settings_admin.settings_presentation.is_key_sensitive",
            return_value=False,
        ),
        patch(
            "micboard.forms.settings_admin.matches_definition_scope",
            return_value=False,
        ),
        pytest.raises(forms.ValidationError, match="does not match"),
    ):
        SettingValueForm.clean(form)
    form.add_error.assert_called_once()


def test_setting_value_clean_rejects_unauthorized_scope_without_definition() -> None:
    cleaned_data = {"definition": None, "value": ""}
    form = _fake_setting_value(cleaned_data)
    with (
        patch("django.forms.models.BaseModelForm.clean", return_value=cleaned_data),
        patch(
            "micboard.forms.settings_admin.settings_visibility.can_manage_scope", return_value=False
        ),
        pytest.raises(forms.ValidationError, match="cannot manage"),
    ):
        SettingValueForm.clean(form)
