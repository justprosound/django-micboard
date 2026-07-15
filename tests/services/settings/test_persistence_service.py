"""Persistence, authorization, and cache contracts for setting overrides."""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError

import pytest

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import (
    SettingsVisibilityScope,
    SettingsWriteRequest,
    SettingWriteItem,
    SettingWriteTarget,
)
from micboard.services.settings.persistence_service import SettingsPersistenceService

pytestmark = pytest.mark.django_db


def _definition(*, key: str, scope: str = "global") -> SettingDefinition:
    return SettingDefinition.objects.create(
        key=key,
        label=key.replace("_", " ").title(),
        scope=scope,
        setting_type=SettingDefinition.TYPE_INTEGER,
        default_value="1",
    )


def test_save_handles_mixed_identifiers_and_redacts_item_failures(monkeypatch) -> None:
    """One query plan handles ID/key items, ignores foreign scope, and reports safe errors."""
    good = _definition(key="good_value")
    broken = _definition(key="broken_value")
    foreign = _definition(key="foreign_value", scope="manufacturer")
    original_serialize = SettingDefinition.serialize_value

    def serialize(definition: SettingDefinition, value: object) -> str:
        if definition.pk == broken.pk:
            raise ValueError("private serialization detail")
        return original_serialize(definition, value)

    monkeypatch.setattr(SettingDefinition, "serialize_value", serialize)
    request = SettingsWriteRequest(
        target=SettingWriteTarget(scope="global"),
        items=[
            SettingWriteItem(definition_id=good.pk, value=7),
            SettingWriteItem(key="broken_value", value=8, label="broken_field"),
            SettingWriteItem(definition_id=foreign.pk, value=9),
            SettingWriteItem(key="missing_value", value=10),
        ],
    )

    with patch(
        "micboard.services.settings.persistence_service.settings.invalidate_value_cache"
    ) as invalidate:
        result = SettingsPersistenceService.save(
            request=request,
            visibility_scope=SettingsVisibilityScope(),
        )

    assert result.saved == 1
    assert result.errors == [
        "Error saving broken_field (ValueError); details redacted.",
        "Setting definition not found for missing_value",
    ]
    assert "private serialization detail" not in str(result)
    assert Setting.objects.get(definition=good).value == "7"
    assert not Setting.objects.filter(definition=foreign).exists()
    invalidate.assert_called_once_with("good_value")


def test_save_rejects_target_outside_management_scope() -> None:
    """The service reauthorizes scope even when a caller bypasses form validation."""
    request = SettingsWriteRequest(
        target=SettingWriteTarget(scope="site", site_id=9),
        items=[],
    )

    with pytest.raises(ValidationError, match="cannot manage"):
        SettingsPersistenceService.save(
            request=request,
            visibility_scope=SettingsVisibilityScope(site_ids=frozenset({1})),
        )


def test_write_target_rejects_mixed_or_missing_identifiers() -> None:
    """DTO validation prevents ambiguous rows from reaching the ORM."""
    with pytest.raises(ValueError, match="does not match"):
        SettingWriteTarget(scope="organization")
    with pytest.raises(ValueError, match="does not match"):
        SettingWriteTarget(scope="site", site_id=1, manufacturer_id=2)
