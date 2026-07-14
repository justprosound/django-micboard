"""Settings registry service for accessing typed, explicitly scoped values."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Protocol

from django.core.cache import cache

from micboard.settings.scope_policy import resolve_scope

logger = logging.getLogger(__name__)


class SettingsScopeReference(Protocol):
    """Minimal model contract required to identify one settings scope."""

    pk: Any


class SettingNotFoundError(Exception):
    """Raised when a required setting cannot be resolved."""

    pass


class SettingsRegistry:
    """Centralized settings accessor honoring each definition's declared scope."""

    CACHE_TTL = 300  # 5 minutes
    _GLOBAL_VERSION_CACHE_KEY = "settings-version:all"
    _GLOBAL_DEFINITION_VERSION_CACHE_KEY = "settings-definition-version:all"
    _setting_definitions_cache: dict[str, tuple[str, Any]] = {}

    @staticmethod
    def get(
        key: str,
        default: Any = None,
        *,
        organization: SettingsScopeReference | None = None,
        site: SettingsScopeReference | None = None,
        manufacturer: SettingsScopeReference | None = None,
        required: bool = False,
        include_definition_default: bool = True,
    ) -> Any:
        """Get a setting value at its definition's declared scope.

        Resolution order:
        1. Stored value at the definition's exact scope
        2. SettingDefinition default, when requested
        3. User-provided default
        4. Raise if required

        Args:
            key: Setting key
            default: Fallback default value
            organization: Organization for scope (MSP mode)
            site: Site for scope (multi-site mode)
            manufacturer: Manufacturer for scope
            required: Raise error if not found
            include_definition_default: Whether to use the registered definition default

        Returns:
            Resolved setting value

        Raises:
            SettingNotFoundError: If required=True and not found
        """
        cache_key = SettingsRegistry._build_cache_key(
            key,
            organization,
            site,
            manufacturer,
            include_definition_default=include_definition_default,
        )

        # Try cache first
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Try the one database scope declared by the setting definition.
        value = SettingsRegistry._resolve_scoped_value(key, organization, site, manufacturer)

        if value is not None:
            cache.set(cache_key, value, SettingsRegistry.CACHE_TTL)
            return value

        if include_definition_default:
            not_found = object()
            parsed = SettingsRegistry.get_definition_default(key, default=not_found)
            if parsed is not not_found:
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
    def get_definition_default(key: str, *, default: Any = None) -> Any:
        """Return the typed definition default without consulting stored values."""
        definition = SettingsRegistry._get_definition(key)
        if definition is None or not definition.default_value:
            return default
        return definition.parse_value(definition.default_value)

    @staticmethod
    def set(
        key: str,
        value: Any,
        *,
        organization: SettingsScopeReference | None = None,
        site: SettingsScopeReference | None = None,
        manufacturer: SettingsScopeReference | None = None,
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
                "scope": "global",
            },
        )

        target = {
            "organization_id": organization.pk if organization else None,
            "site_id": site.pk if site else None,
            "manufacturer_id": manufacturer.pk if manufacturer else None,
        }
        target_scope = resolve_scope(**target)
        if target_scope is None:
            raise ValueError("A setting value must target exactly one scope")
        if created and definition.scope != target_scope:
            definition.scope = target_scope
            definition.save(update_fields=["scope"])
        elif definition.scope != target_scope:
            raise ValueError(
                f"Setting {key!r} requires {definition.scope!r} scope, not {target_scope!r}"
            )

        # Get or create setting value
        setting, created = Setting.objects.get_or_create(
            definition=definition,
            **target,
            defaults={"value": definition.serialize_value(value)},
        )

        if not created:
            setting.set_value(value)
            setting.save()

        SettingsRegistry.invalidate_cache(key)
        logger.info("Set setting %s", key)

    @staticmethod
    def get_all_for_scope(
        *,
        organization: SettingsScopeReference | None = None,
        site: SettingsScopeReference | None = None,
        manufacturer: SettingsScopeReference | None = None,
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

        target = {
            "organization_id": organization.pk if organization else None,
            "site_id": site.pk if site else None,
            "manufacturer_id": manufacturer.pk if manufacturer else None,
        }
        settings_qs = Setting.objects.filter(**target).select_related("definition")

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
            cache.set(
                SettingsRegistry._version_cache_key(key),
                secrets.token_hex(8),
                timeout=None,
            )
        else:
            cache.set(
                SettingsRegistry._GLOBAL_VERSION_CACHE_KEY,
                secrets.token_hex(8),
                timeout=None,
            )
            SettingsRegistry._setting_definitions_cache.clear()

    @staticmethod
    def invalidate_definition(key: str | None = None) -> None:
        """Invalidate cached definition metadata and all values derived from it."""
        if key is None:
            cache.set(
                SettingsRegistry._GLOBAL_DEFINITION_VERSION_CACHE_KEY,
                secrets.token_hex(8),
                timeout=None,
            )
            SettingsRegistry._setting_definitions_cache.clear()
            SettingsRegistry.invalidate_cache()
            return
        SettingsRegistry._setting_definitions_cache.pop(key, None)
        cache.set(
            SettingsRegistry._definition_version_cache_key(key),
            secrets.token_hex(8),
            timeout=None,
        )
        SettingsRegistry.invalidate_cache(key)

    @staticmethod
    def _resolve_scoped_value(
        key: str,
        organization: SettingsScopeReference | None,
        site: SettingsScopeReference | None,
        manufacturer: SettingsScopeReference | None,
    ) -> Any | None:
        """Resolve only the value matching the definition's declared scope."""
        from micboard.models.settings.registry import Setting, SettingDefinition

        definition = SettingsRegistry._get_definition(key)
        if definition is None:
            return None

        filters: dict[str, Any] = {
            "definition": definition,
            "organization_id": None,
            "site_id": None,
            "manufacturer_id": None,
        }
        if definition.scope == SettingDefinition.SCOPE_ORGANIZATION:
            if organization is None:
                return None
            filters["organization_id"] = organization.pk
        elif definition.scope == SettingDefinition.SCOPE_SITE:
            if site is None:
                return None
            filters["site_id"] = site.pk
        elif definition.scope == SettingDefinition.SCOPE_MANUFACTURER:
            if manufacturer is None:
                return None
            filters["manufacturer_id"] = manufacturer.pk
        elif definition.scope != SettingDefinition.SCOPE_GLOBAL:
            return None

        try:
            setting = Setting.objects.get(**filters)
        except Setting.DoesNotExist:
            return None
        return setting.get_parsed_value()

    @staticmethod
    def _get_definition(key: str) -> Any | None:
        """Get setting definition by key (with caching)."""
        from micboard.models.settings import SettingDefinition

        version = SettingsRegistry._definition_version(key)
        cached = SettingsRegistry._setting_definitions_cache.get(key)
        if cached is not None and cached[0] == version:
            return cached[1]

        try:
            definition = SettingDefinition.objects.get(key=key)
            SettingsRegistry._setting_definitions_cache[key] = (version, definition)
            return definition
        except SettingDefinition.DoesNotExist:
            return None

    @staticmethod
    def _build_cache_key(
        key: str,
        organization: SettingsScopeReference | None,
        site: SettingsScopeReference | None,
        manufacturer: SettingsScopeReference | None,
        *,
        include_definition_default: bool = True,
    ) -> str:
        """Build cache key from setting and scopes."""
        global_version = cache.get(SettingsRegistry._GLOBAL_VERSION_CACHE_KEY)
        if global_version is None:
            cache.add(SettingsRegistry._GLOBAL_VERSION_CACHE_KEY, "0", timeout=None)
            global_version = cache.get(SettingsRegistry._GLOBAL_VERSION_CACHE_KEY, "0")
        version_key = SettingsRegistry._version_cache_key(key)
        version = cache.get(version_key)
        if version is None:
            cache.add(version_key, "0", timeout=None)
            version = cache.get(version_key, "0")
        org_id = organization.pk if organization else "g"
        site_id = site.pk if site else "g"
        mfg_id = manufacturer.pk if manufacturer else "g"
        default_mode = "definition" if include_definition_default else "stored"
        return (
            f"settings:{global_version}:{key}:{version}:{default_mode}:{org_id}:{site_id}:{mfg_id}"
        )

    @staticmethod
    def _version_cache_key(key: str) -> str:
        """Return the shared generation key used to invalidate every scoped cache entry."""
        return f"settings-version:{key}"

    @staticmethod
    def _definition_version_cache_key(key: str) -> str:
        """Return the shared generation key for one definition's metadata."""
        return f"settings-definition-version:{key}"

    @staticmethod
    def _definition_version(key: str) -> str:
        """Return shared global and per-definition metadata generations."""
        global_version = cache.get(SettingsRegistry._GLOBAL_DEFINITION_VERSION_CACHE_KEY)
        if global_version is None:
            cache.add(SettingsRegistry._GLOBAL_DEFINITION_VERSION_CACHE_KEY, "0", timeout=None)
            global_version = cache.get(
                SettingsRegistry._GLOBAL_DEFINITION_VERSION_CACHE_KEY,
                "0",
            )
        version_key = SettingsRegistry._definition_version_cache_key(key)
        version = cache.get(version_key)
        if version is None:
            cache.add(version_key, "0", timeout=None)
            version = cache.get(version_key, "0")
        return f"{global_version}:{version}"
