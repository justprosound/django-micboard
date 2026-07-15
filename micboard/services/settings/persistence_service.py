"""Authorized persistence for database-backed setting overrides."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import (
    SettingsVisibilityScope,
    SettingsWriteRequest,
    SettingsWriteResult,
    SettingWriteItem,
)
from micboard.services.settings.settings_service import settings
from micboard.services.settings.visibility_service import settings_visibility
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class SettingsPersistenceService:
    """Own authorization, serialization, upsert, and cache invalidation."""

    @classmethod
    def save(
        cls,
        *,
        request: SettingsWriteRequest,
        visibility_scope: SettingsVisibilityScope,
    ) -> SettingsWriteResult:
        """Persist a best-effort batch under one exact authorized scope."""
        target = request.target
        if not settings_visibility.can_manage_scope(
            visibility_scope,
            organization_id=target.organization_id,
            site_id=target.site_id,
            manufacturer_id=target.manufacturer_id,
        ):
            raise ValidationError("You cannot manage settings for the selected scope")

        definitions = cls._definitions_for(request)
        definition_by_id = {definition.pk: definition for definition in definitions}
        definition_by_key = {definition.key: definition for definition in definitions}
        result = SettingsWriteResult()
        for item in request.items:
            definition = (
                definition_by_id.get(item.definition_id)
                if item.definition_id is not None
                else definition_by_key.get(item.key or "")
            )
            if definition is None:
                if item.key is not None:
                    result.errors.append(f"Setting definition not found for {item.key}")
                continue
            try:
                cls._upsert(definition=definition, item=item, request=request)
            except Exception as exc:
                logger.exception(
                    "Setting override persistence failed for definition %s",
                    definition.pk,
                    exc_info=sanitized_exception_info(exc),
                )
                label = definition.label if item.definition_id is not None else item.label
                result.errors.append(
                    f"Error saving {label} ({type(exc).__name__}); details redacted."
                )
            else:
                result.saved += 1
                settings.invalidate_value_cache(definition.key)
        return result

    @staticmethod
    def _definitions_for(request: SettingsWriteRequest) -> list[SettingDefinition]:
        """Fetch all active in-scope definitions for one write batch."""
        definition_ids = [
            item.definition_id for item in request.items if item.definition_id is not None
        ]
        keys = [item.key for item in request.items if item.key is not None]
        queryset = SettingDefinition.objects.filter(
            is_active=True,
            scope=request.target.scope,
        )
        identifiers = Q()
        if definition_ids:
            identifiers |= Q(pk__in=definition_ids)
        if keys:
            identifiers |= Q(key__in=keys)
        return list(queryset.filter(identifiers)) if identifiers else []

    @staticmethod
    def _upsert(
        *,
        definition: SettingDefinition,
        item: SettingWriteItem,
        request: SettingsWriteRequest,
    ) -> None:
        """Serialize and upsert one setting override."""
        target = request.target
        lookup: dict[str, Any] = {
            "definition": definition,
            "organization_id": target.organization_id,
            "site_id": target.site_id,
            "manufacturer_id": target.manufacturer_id,
        }
        Setting.objects.update_or_create(
            **lookup,
            defaults={"value": definition.serialize_value(item.value)},
        )
