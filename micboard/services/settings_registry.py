"""Settings registry service for accessing configuration values with scope resolution.

Provides a unified interface for getting settings with fallback through scope hierarchy:
Global → Organization → Site → Manufacturer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from django.core.cache import cache

if TYPE_CHECKING:
    from micboard.models import Manufacturer, Organization, Site

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SettingNotFoundError(Exception):
    """Raised when a required setting cannot be resolved."""

    pass


class SettingsRegistry:
    """Centralized settings accessor with scope-aware fallback."""

    CACHE_TTL = 300  # 5 minutes
    _setting_definitions_cache: dict[str, Any] = {}

    @staticmethod
    def get(
        key: str,
        default: Any = None,
        *,
        organization: Organization | None = None,
        site: Site | None = None,
        manufacturer: Manufacturer | None = None,
        required: bool = False,
    ) -> Any:
        """Get a setting value with scope-aware fallback.

        Resolution order:
        1. Specific scope (org/site/manufacturer)
        2. Move up hierarchy
        3. Global default
        4. SettingDefinition default
        5. User-provided default
        6. Raise if required

        Args:
            key: Setting key
            default: Fallback default value
            organization: Organization for scope (MSP mode)
            site: Site for scope (multi-site mode)
            manufacturer: Manufacturer for scope
            required: Raise error if not found

        Returns:
            Resolved setting value

        Raises:
            SettingNotFoundError: If required=True and not found
        """
        cache_key = SettingsRegistry._build_cache_key(key, organization, site, manufacturer)

        # Try cache first
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Try to get from database with scope hierarchy
        value = SettingsRegistry._resolve_scoped_value(key, organization, site, manufacturer)

        if value is not None:
            cache.set(cache_key, value, SettingsRegistry.CACHE_TTL)
            return value

        # Try to get definition default
        definition = SettingsRegistry._get_definition(key)
        if definition and definition.default_value:
            parsed = definition.parse_value(definition.default_value)
            cache.set(cache_key, parsed, SettingsRegistry.CACHE_TTL)
            return parsed

        # Use provided default
        if default is not None:
            cache.set(cache_key, default, SettingsRegistry.CACHE_TTL)
            return default

        # Required but not found
        if required:
            raise SettingNotFoundError(f"Required setting '{key}' not found")

        return None

    @staticmethod
    def set(
        key: str,
        value: Any,
        *,
        organization: Organization | None = None,
        site: Site | None = None,
        manufacturer: Manufacturer | None = None,
    ) -> None:
        """Set a setting value at a specific scope.

        Args:
            key: Setting key
            value: Value to set
            organization: Organization scope (MSP mode)
            site: Site scope (multi-site mode)
            manufacturer: Manufacturer scope
        """
        from micboard.models.settings import Setting, SettingDefinition

        # Get or create definition
        definition, created = SettingDefinition.objects.get_or_create(
            key=key,
            defaults={
                "label": key.replace("_", " ").title(),
                "scope": SettingDefinition.SCOPE_GLOBAL,
            },
        )

        # Get or create setting value
        setting, created = Setting.objects.get_or_create(
            definition=definition,
            organization=organization,
            site=site,
            manufacturer=manufacturer,
            defaults={"value": definition.serialize_value(value)},
        )

        if not created:
            setting.set_value(value)
            setting.save()

        # Clear cache
        cache_key = SettingsRegistry._build_cache_key(key, organization, site, manufacturer)
        cache.delete(cache_key)
        logger.info(f"Set setting {key} = {value}")

    @staticmethod
    def get_all_for_scope(
        *,
        organization: Organization | None = None,
        site: Site | None = None,
        manufacturer: Manufacturer | None = None,
    ) -> dict[str, Any]:
        """Get all settings for a specific scope.

        Args:
            organization: Organization scope
            site: Site scope
            manufacturer: Manufacturer scope

        Returns:
            Dict of all setting keys and values for scope
        """
        from micboard.models.settings import Setting

        settings_qs = Setting.objects.filter(
            organization=organization,
            site=site,
            manufacturer=manufacturer,
        ).select_related("definition")

        result = {}
        for setting in settings_qs:
            result[setting.definition.key] = setting.get_parsed_value()

        return result

    @staticmethod
    def invalidate_cache(key: str | None = None) -> None:
        """Invalidate settings cache.

        Args:
            key: Specific key to invalidate, or None for all
        """
        if key:
            # Note: cache.delete_pattern may not be available on all backends
            # This is a simplified version; in production use cache.clear() or Redis
            cache.delete(SettingsRegistry._build_cache_key(key, None, None, None))
        else:
            # Clear all settings-related cache
            cache.clear()

    @staticmethod
    def _resolve_scoped_value(
        key: str,
        organization: Organization | None,
        site: Site | None,
        manufacturer: Manufacturer | None,
    ) -> Any | None:
        """Resolve setting value through scope hierarchy.

        Resolution order:
        1. Specific scope (org/site/manufacturer)
        2. Site-wide (if not already site-specific)
        3. Organization-wide (if not already org-specific)
        4. Global
        """
        from micboard.models.settings import Setting

        # Try manufacturer scope
        if manufacturer:
            try:
                setting = Setting.objects.select_related("definition").get(
                    definition__key=key,
                    manufacturer=manufacturer,
                    organization=None,
                    site=None,
                )
                return setting.get_parsed_value()
            except Setting.DoesNotExist:
                pass

        # Try site scope
        if site:
            try:
                setting = Setting.objects.select_related("definition").get(
                    definition__key=key,
                    site=site,
                    organization=None,
                    manufacturer=None,
                )
                return setting.get_parsed_value()
            except Setting.DoesNotExist:
                pass

        # Try organization scope
        if organization:
            try:
                setting = Setting.objects.select_related("definition").get(
                    definition__key=key,
                    organization=organization,
                    site=None,
                    manufacturer=None,
                )
                return setting.get_parsed_value()
            except Setting.DoesNotExist:
                pass

        # Try global scope
        try:
            setting = Setting.objects.select_related("definition").get(
                definition__key=key,
                organization=None,
                site=None,
                manufacturer=None,
            )
            return setting.get_parsed_value()
        except Setting.DoesNotExist:
            pass

        return None

    @staticmethod
    def _get_definition(key: str) -> Any | None:
        """Get setting definition by key (with caching)."""
        from micboard.models.settings import SettingDefinition

        if key in SettingsRegistry._setting_definitions_cache:
            return SettingsRegistry._setting_definitions_cache[key]

        try:
            definition = SettingDefinition.objects.get(key=key)
            SettingsRegistry._setting_definitions_cache[key] = definition
            return definition
        except SettingDefinition.DoesNotExist:
            return None

    @staticmethod
    def _build_cache_key(
        key: str,
        organization: Organization | None,
        site: Site | None,
        manufacturer: Manufacturer | None,
    ) -> str:
        """Build cache key from setting and scopes."""
        org_id = organization.id if organization else "g"
        site_id = site.id if site else "g"
        mfg_id = manufacturer.id if manufacturer else "g"
        return f"settings:{key}:{org_id}:{site_id}:{mfg_id}"
