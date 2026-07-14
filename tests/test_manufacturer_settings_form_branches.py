"""Focused access and persistence coverage for manufacturer settings forms."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError

import pytest

from micboard.forms.settings import ManufacturerSettingsForm
from micboard.services.settings.dtos import SettingsVisibilityScope, SettingsWriteResult


def _fake_manufacturer_form(cleaned_data: dict[str, Any]) -> ManufacturerSettingsForm:
    form = object.__new__(ManufacturerSettingsForm)
    form.cleaned_data = cleaned_data
    form.visibility_scope = SettingsVisibilityScope()
    return form


def test_manufacturer_form_init_limits_queryset() -> None:
    scope = SettingsVisibilityScope(manufacturer_ids=frozenset({3}))
    with (
        patch("micboard.forms.settings._scope_for_user", return_value=scope),
        patch("micboard.models.discovery.manufacturer.Manufacturer.objects.all") as all_mfg,
    ):
        ManufacturerSettingsForm(user=object())
    all_mfg.return_value.filter.assert_called_once_with(pk__in=frozenset({3}))


def test_manufacturer_save_rejects_invalid_or_unauthorized_form() -> None:
    form = _fake_manufacturer_form({})
    form.is_valid = Mock(return_value=False)
    with pytest.raises(ValidationError, match="not valid"):
        form.save_settings()

    form.cleaned_data = {"manufacturer": SimpleNamespace(pk=5)}
    form.is_valid = Mock(return_value=True)
    with (
        patch("micboard.forms.settings.settings_visibility.can_manage_scope", return_value=False),
        pytest.raises(ValidationError, match="cannot manage"),
    ):
        form.save_settings()


def test_manufacturer_save_skips_blanks_saves_and_classifies_errors() -> None:
    manufacturer = SimpleNamespace(pk=5)
    form = _fake_manufacturer_form(
        {
            "manufacturer": manufacturer,
            "battery_good_level": 80,
            "battery_low_level": 20,
            "battery_critical_level": 10,
        }
    )
    form.is_valid = Mock(return_value=True)
    result = SettingsWriteResult(
        saved=1,
        errors=[
            "Setting definition not found for battery_low_level",
            "Error saving battery_critical_level (ValueError); details redacted.",
        ],
    )
    with (
        patch("micboard.forms.settings.settings_visibility.can_manage_scope", return_value=True),
        patch(
            "micboard.forms.settings.SettingsPersistenceService.save",
            return_value=result,
        ) as save,
    ):
        results = form.save_settings()

    assert results["saved"] == 1
    assert results["errors"] == [
        "Setting definition not found for battery_low_level",
        "Error saving battery_critical_level (ValueError); details redacted.",
    ]
    assert "bad serialize" not in str(results)
    request = save.call_args.kwargs["request"]
    assert request.target.manufacturer_id == 5
    assert [item.key for item in request.items] == [
        "battery_good_level",
        "battery_low_level",
        "battery_critical_level",
    ]
