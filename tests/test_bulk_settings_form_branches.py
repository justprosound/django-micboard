"""Focused scope, field, validation, and persistence coverage for bulk settings forms."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django import forms
from django.core.exceptions import ValidationError

import pytest

from micboard.forms.settings import (
    BulkSettingConfigForm,
    _has_choices,
    _optional_boolean_field,
    _scope_for_user,
)
from micboard.forms.settings_admin import _scope_for_user as _admin_scope_for_user
from micboard.models.settings.registry import SettingDefinition
from micboard.services.settings.dtos import SettingsVisibilityScope, SettingsWriteResult
from micboard.services.settings.persistence_service import SettingsPersistenceService


def test_scope_helpers_and_optional_boolean_contract() -> None:
    assert _scope_for_user(None) == SettingsVisibilityScope()
    assert _admin_scope_for_user(None) == SettingsVisibilityScope()
    user = object()
    scope = SettingsVisibilityScope(site_ids=frozenset({1}))
    with patch(
        "micboard.forms.settings.settings_visibility.for_management_user",
        return_value=scope,
    ) as bulk:
        assert _scope_for_user(user) is scope
    with patch(
        "micboard.forms.settings_admin.settings_visibility.for_management_user",
        return_value=scope,
    ) as admin:
        assert _admin_scope_for_user(user) is scope
    bulk.assert_called_once_with(user=user)
    admin.assert_called_once_with(user=user)
    assert _has_choices(None) is True
    assert _has_choices(frozenset()) is False
    assert _has_choices(frozenset({1})) is True
    field = _optional_boolean_field(label="Enabled", help_text="help")
    assert field.clean("") is None
    assert field.clean("true") is True
    assert field.clean("false") is False


def _fake_bulk_form(cleaned_data: dict[str, Any]) -> BulkSettingConfigForm:
    form = object.__new__(BulkSettingConfigForm)
    form.cleaned_data = cleaned_data
    form.visibility_scope = SettingsVisibilityScope()
    return form


def test_bulk_form_init_removes_uninstalled_org_and_restricts_dimensions() -> None:
    scope = SettingsVisibilityScope(
        organization_ids=frozenset(),
        site_ids=frozenset({2}),
        manufacturer_ids=frozenset({3}),
    )
    with (
        patch("micboard.forms.settings._scope_for_user", return_value=scope),
        patch("micboard.forms.settings.settings_visibility.is_unrestricted", return_value=False),
        patch("micboard.forms.settings.apps.is_installed", return_value=False),
        patch("micboard.forms.settings.Site.objects.all") as sites,
        patch("micboard.models.discovery.manufacturer.Manufacturer.objects.all") as manufacturers,
        patch.object(BulkSettingConfigForm, "_add_setting_fields"),
    ):
        form = BulkSettingConfigForm(user=object())

    assert "organization" not in form.fields
    sites.return_value.filter.assert_called_once_with(pk__in=frozenset({2}))
    manufacturers.return_value.filter.assert_called_once_with(pk__in=frozenset({3}))
    assert [value for value, _label in form.fields["scope"].choices] == [
        "",
        "site",
        "manufacturer",
    ]


def test_bulk_form_init_scopes_installed_organizations() -> None:
    scope = SettingsVisibilityScope(organization_ids=frozenset({4}))
    with (
        patch("micboard.forms.settings._scope_for_user", return_value=scope),
        patch("micboard.forms.settings.settings_visibility.is_unrestricted", return_value=False),
        patch("micboard.forms.settings.apps.is_installed", return_value=True),
        patch("micboard.multitenancy.models.Organization._default_manager.all") as organizations,
        patch.object(BulkSettingConfigForm, "_add_setting_fields"),
    ):
        form = BulkSettingConfigForm(user=object())
    organizations.return_value.filter.assert_called_once_with(pk__in=frozenset({4}))
    assert "organization" in form.fields


@pytest.mark.parametrize(
    ("setting_type", "expected_type"),
    [
        (SettingDefinition.TYPE_BOOLEAN, forms.TypedChoiceField),
        (SettingDefinition.TYPE_INTEGER, forms.IntegerField),
        (SettingDefinition.TYPE_CHOICES, forms.ChoiceField),
        (SettingDefinition.TYPE_JSON, forms.JSONField),
        (SettingDefinition.TYPE_STRING, forms.CharField),
    ],
)
def test_bulk_form_adds_field_matching_each_definition_type(
    setting_type: str, expected_type: type[forms.Field]
) -> None:
    definition = SimpleNamespace(
        id=1,
        setting_type=setting_type,
        description="",
        label="Example",
        choices_json={"one": "One"} if setting_type == SettingDefinition.TYPE_CHOICES else None,
        get_setting_type_display=lambda: setting_type,
    )
    definitions = MagicMock()
    definitions.order_by.return_value = definitions
    definitions.filter.return_value = [definition]
    fake = SimpleNamespace(
        fields={},
        data={"scope": "manufacturer"},
        is_bound=True,
        add_prefix=lambda name: name,
    )
    with patch(
        "micboard.forms.settings.SettingDefinition.objects.filter", return_value=definitions
    ):
        BulkSettingConfigForm._add_setting_fields(fake)
    assert isinstance(fake.fields["setting_1"], expected_type)


def test_bulk_form_adds_fields_without_bound_scope_filter() -> None:
    definition = SimpleNamespace(
        id=2,
        setting_type=SettingDefinition.TYPE_CHOICES,
        description="description",
        label="Example",
        choices_json=None,
        get_setting_type_display=lambda: "choices",
    )
    definitions = MagicMock()
    definitions.order_by.return_value = [definition]
    fake = SimpleNamespace(fields={}, data={}, is_bound=False, add_prefix=lambda name: name)
    with patch(
        "micboard.forms.settings.SettingDefinition.objects.filter", return_value=definitions
    ):
        BulkSettingConfigForm._add_setting_fields(fake)
    assert list(fake.fields["setting_2"].choices) == [("", "---")]


@pytest.mark.parametrize(
    ("cleaned_data", "installed", "message"),
    [
        ({"scope": "organization"}, False, "requires"),
        ({"scope": "organization"}, True, "Organization is required"),
        ({"scope": "site"}, True, "Site is required"),
        ({"scope": "manufacturer"}, True, "Manufacturer is required"),
    ],
)
def test_bulk_form_clean_requires_scope_target(
    cleaned_data: dict[str, Any], installed: bool, message: str
) -> None:
    form = _fake_bulk_form(cleaned_data)
    with (
        patch("django.forms.Form.clean", return_value=cleaned_data),
        patch("micboard.forms.settings.apps.is_installed", return_value=installed),
        pytest.raises(ValidationError, match=message),
    ):
        form.clean()


@pytest.mark.parametrize(
    ("scope", "target_key"),
    [("organization", "organization"), ("site", "site"), ("manufacturer", "manufacturer")],
)
def test_bulk_form_clean_authorizes_effective_scope(scope: str, target_key: str) -> None:
    target = SimpleNamespace(pk=9)
    cleaned_data = {"scope": scope, target_key: target}
    form = _fake_bulk_form(cleaned_data)
    with (
        patch("django.forms.Form.clean", return_value=cleaned_data),
        patch("micboard.forms.settings.apps.is_installed", return_value=True),
        patch(
            "micboard.forms.settings.settings_visibility.can_manage_scope", return_value=True
        ) as can_manage,
    ):
        assert form.clean() == cleaned_data
    expected = {
        "organization_id": 9 if scope == "organization" else None,
        "site_id": 9 if scope == "site" else None,
        "manufacturer_id": 9 if scope == "manufacturer" else None,
    }
    can_manage.assert_called_once_with(form.visibility_scope, **expected)


def test_bulk_form_clean_denies_scope() -> None:
    cleaned_data = {"scope": SettingDefinition.SCOPE_GLOBAL}
    form = _fake_bulk_form(cleaned_data)
    with (
        patch("django.forms.Form.clean", return_value=cleaned_data),
        patch("micboard.forms.settings.settings_visibility.can_manage_scope", return_value=False),
        pytest.raises(ValidationError, match="cannot manage"),
    ):
        form.clean()


def test_bulk_save_rejects_invalid_form_skips_blanks_saves_and_collects_errors() -> None:
    form = _fake_bulk_form({})
    form.is_valid = Mock(return_value=False)
    with pytest.raises(ValidationError, match="not valid"):
        form.save_settings()

    organization = SimpleNamespace(pk=2)
    form.cleaned_data = {
        "scope": SettingDefinition.SCOPE_ORGANIZATION,
        "organization": organization,
        "setting_1": 4,
        "setting_2": 5,
        "setting_3": "",
    }
    form.is_valid = Mock(return_value=True)
    result = SettingsWriteResult(
        saved=1,
        errors=["Error saving Bad (ValueError); details redacted."],
    )
    with patch.object(
        SettingsPersistenceService,
        "save",
        return_value=result,
    ) as save:
        results = form.save_settings()

    assert results["saved"] == 1
    assert results["errors"] == ["Error saving Bad (ValueError); details redacted."]
    assert "invalid" not in str(results)
    request = save.call_args.kwargs["request"]
    assert request.target.organization_id == 2
    assert [item.definition_id for item in request.items] == [1, 2]
