"""Unified settings resolution service.

Composes Django settings, feature flags, AppConfig defaults, and the
DB-backed SettingsRegistry into a single resolution chain.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.conf import settings as django_settings

from micboard.apps import MicboardConfig
from micboard.models.settings import Setting, SettingDefinition
from micboard.services.shared.settings_registry import SettingsRegistry as _SettingsRegistry

logger = logging.getLogger(__name__)


class SettingsService:
    """Unified settings resolution with multi-source fallback.

    Resolution order for ``get()``:

    1. DB Setting with scope (org/site/manufacturer) via ``SettingsRegistry``
    2. ``settings.MICBOARD_CONFIG`` dict key
    3. Feature flag Django setting (``MICBOARD_*``) via key mapping
    4. ``MicboardConfig.default_config`` (``POLL_INTERVAL``, etc.)
    5. Provided *default*
    """

    # Canonical key → Django setting name for feature flag properties
    _FEATURE_FLAG_KEYS: dict[str, str] = {
        "msp_enabled": "MICBOARD_MSP_ENABLED",
        "multi_site_mode": "MICBOARD_MULTI_SITE_MODE",
        "site_isolation": "MICBOARD_SITE_ISOLATION",
        "allow_cross_org_view": "MICBOARD_ALLOW_CROSS_ORG_VIEW",
        "allow_org_switching": "MICBOARD_ALLOW_ORG_SWITCHING",
        "subdomain_routing": "MICBOARD_SUBDOMAIN_ROUTING",
        "root_domain": "MICBOARD_ROOT_DOMAIN",
        "admin_org_selector": "MICBOARD_ADMIN_ORG_SELECTOR",
        "global_device_limit": "MICBOARD_GLOBAL_DEVICE_LIMIT",
        "device_limit_warning_threshold": "MICBOARD_DEVICE_LIMIT_WARNING_THRESHOLD",
        "activity_log_retention_days": "MICBOARD_ACTIVITY_LOG_RETENTION_DAYS",
        "service_sync_log_retention_days": "MICBOARD_SERVICE_SYNC_LOG_RETENTION_DAYS",
        "api_health_log_retention_days": "MICBOARD_API_HEALTH_LOG_RETENTION_DAYS",
        "audit_archive_path": "MICBOARD_AUDIT_ARCHIVE_PATH",
    }

    def __init__(self) -> None:
        self._registry = _SettingsRegistry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        key: str,
        default: Any = None,
        *,
        organization: Any = None,
        site: Any = None,
        manufacturer: Any = None,
    ) -> Any:
        """Resolve a setting value through the multi-source fallback chain.

        Args:
            key: Canonical setting key.
            default: Fallback if not found in any source.
            organization: Scope hint for DB-backed setting.
            site: Scope hint for DB-backed setting.
            manufacturer: Scope hint for DB-backed setting.

        Returns:
            Resolved value or *default*.
        """
        value = self._registry.get(
            key,
            default=None,
            organization=organization,
            site=site,
            manufacturer=manufacturer,
        )
        if value is not None:
            return value

        micboard_config = getattr(django_settings, "MICBOARD_CONFIG", {})
        if key in micboard_config:
            return micboard_config[key]

        flag_name = self._FEATURE_FLAG_KEYS.get(key)
        if flag_name is not None and hasattr(django_settings, flag_name):
            return getattr(django_settings, flag_name)

        app_default = MicboardConfig.default_config.get(key)
        if app_default is not None:
            return app_default

        return default

    def get_config_dict(self) -> dict[str, Any]:
        """Return MICBOARD_CONFIG merged with AppConfig defaults."""
        micboard_config = getattr(django_settings, "MICBOARD_CONFIG", {})
        return {**MicboardConfig.default_config, **micboard_config}

    @property
    def testing(self) -> bool:
        """Whether Django is running tests."""
        return getattr(django_settings, "TESTING", False)

    # ------------------------------------------------------------------
    # Settings business logic (moved from views/settings.py)
    # ------------------------------------------------------------------

    def _is_sensitive_key(self, key: str) -> bool:
        """Return True when a setting key likely contains secrets."""
        key_lower = key.lower()
        sensitive_tokens = ("secret", "token", "password", "shared_key", "api_key", "key")
        return any(token in key_lower for token in sensitive_tokens)

    def _format_value(self, value: Any, *, sensitive: bool) -> str:
        """Format a value for display in the admin diff view."""
        if value is None:
            return "—"
        if sensitive:
            return "••••••"
        return str(value)

    def _resolve_organization_names(self, org_ids: set[int]) -> dict[int, str]:
        """Resolve organization IDs to names when available."""
        if not apps.is_installed("micboard.multitenancy"):
            return {}

        from micboard.multitenancy.models import Organization

        return dict(Organization._default_manager.filter(id__in=org_ids).values_list("id", "name"))

    def _resolve_manufacturer_names(self, manufacturer_ids: set[int]) -> dict[int, str]:
        """Resolve manufacturer IDs to names when available."""
        try:
            from micboard.models.discovery import Manufacturer
        except Exception:
            return {}

        return dict(Manufacturer.objects.filter(id__in=manufacturer_ids).values_list("id", "name"))

    def get_settings_diff(
        self,
        organization_ids: set[int] | None = None,
        site_ids: set[int] | None = None,
        manufacturer_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        """Show where tenant/site/manufacturer settings differ from global defaults.

        Args:
            organization_ids: Set of organization IDs to consider
            site_ids: Set of site IDs to consider
            manufacturer_ids: Set of manufacturer IDs to consider

        Returns:
            Dictionary containing settings diff data for template rendering
        """
        definitions = SettingDefinition.objects.filter(is_active=True).order_by(
            "scope",
            "key",
        )
        raw_overrides: list[dict[str, Any]] = []

        org_ids_set: set[int] = set() if organization_ids is None else organization_ids
        manufacturer_ids_set: set[int] = set() if manufacturer_ids is None else manufacturer_ids

        for definition in definitions:
            org_overrides = list(
                Setting.objects.filter(definition=definition, organization_id__isnull=False)
            )
            site_overrides = list(
                Setting.objects.filter(definition=definition, site__isnull=False).select_related(
                    "site"
                )
            )
            mfg_overrides = list(
                Setting.objects.filter(definition=definition, manufacturer_id__isnull=False)
            )

            if not (org_overrides or site_overrides or mfg_overrides):
                continue

            org_ids_set.update(
                {override.organization_id for override in org_overrides if override.organization_id}
            )
            manufacturer_ids_set.update(
                {override.manufacturer_id for override in mfg_overrides if override.manufacturer_id}
            )

            global_setting = Setting.objects.filter(
                definition=definition,
                organization_id__isnull=True,
                site__isnull=True,
                manufacturer_id__isnull=True,
            ).first()

            sensitive = self._is_sensitive_key(definition.key)
            global_value = self._format_value(
                global_setting.get_parsed_value() if global_setting else None,
                sensitive=sensitive,
            )

            raw_overrides.append(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "global": global_value,
                    "sensitive": sensitive,
                    "org_overrides": org_overrides,
                    "site_overrides": site_overrides,
                    "mfg_overrides": mfg_overrides,
                }
            )

        org_names = self._resolve_organization_names(org_ids_set)
        mfg_names = self._resolve_manufacturer_names(manufacturer_ids_set)

        overrides: list[dict[str, Any]] = []
        for override in raw_overrides:
            sensitive = override["sensitive"]

            org_items = [
                {
                    "label": org_names.get(item.organization_id, f"Org {item.organization_id}"),
                    "value": self._format_value(item.get_parsed_value(), sensitive=sensitive),
                }
                for item in override["org_overrides"]
            ]

            site_items = [
                {
                    "label": item.site.name if item.site else f"Site {item.site_id}",
                    "value": self._format_value(item.get_parsed_value(), sensitive=sensitive),
                }
                for item in override["site_overrides"]
            ]

            mfg_items = [
                {
                    "label": mfg_names.get(
                        item.manufacturer_id, f"Manufacturer {item.manufacturer_id}"
                    ),
                    "value": self._format_value(item.get_parsed_value(), sensitive=sensitive),
                }
                for item in override["mfg_overrides"]
            ]

            overrides.append(
                {
                    "key": override["key"],
                    "label": override["label"],
                    "global": override["global"],
                    "org_overrides": org_items,
                    "site_overrides": site_items,
                    "mfg_overrides": mfg_items,
                }
            )

        return {
            "title": "Settings Overrides Diff",
            "overrides": overrides,
        }

    def get_settings_overview(self) -> dict[str, Any]:
        """Show overview of all configured settings.

        Returns:
            Dictionary containing settings overview data for template rendering
        """
        # Group stored values by the identifier that establishes their scope.
        global_settings = Setting.objects.filter(
            organization_id__isnull=True,
            site__isnull=True,
            manufacturer_id__isnull=True,
        ).select_related("definition")

        org_settings = Setting.objects.filter(
            organization_id__isnull=False,
        ).select_related("definition")

        site_settings = Setting.objects.filter(
            site__isnull=False,
        ).select_related("definition", "site")

        mfg_settings = Setting.objects.filter(
            manufacturer_id__isnull=False,
        ).select_related("definition")

        return {
            "title": "Settings Overview",
            "global_settings": global_settings,
            "org_settings": org_settings,
            "site_settings": site_settings,
            "mfg_settings": mfg_settings,
        }

    # ------------------------------------------------------------------
    # Feature-flag convenience properties
    # ------------------------------------------------------------------

    @property
    def msp_enabled(self) -> bool:
        return self.get("msp_enabled", False)

    @property
    def multi_site_mode(self) -> bool:
        return self.get("multi_site_mode", False)

    @property
    def site_isolation(self) -> str:
        return self.get("site_isolation", "none")

    @property
    def allow_cross_org_view(self) -> bool:
        return self.get("allow_cross_org_view", True)

    @property
    def allow_org_switching(self) -> bool:
        return self.get("allow_org_switching", True)

    @property
    def subdomain_routing(self) -> bool:
        return self.get("subdomain_routing", False)

    @property
    def root_domain(self) -> str:
        return self.get("root_domain", "")

    @property
    def admin_org_selector(self) -> bool:
        return self.get("admin_org_selector", True)

    @property
    def global_device_limit(self) -> int | None:
        return self.get("global_device_limit", None)

    @property
    def device_limit_warning_threshold(self) -> float:
        return self.get("device_limit_warning_threshold", 0.9)

    @property
    def activity_log_retention_days(self) -> int:
        return self.get("activity_log_retention_days", 90)

    @property
    def service_sync_log_retention_days(self) -> int:
        return self.get("service_sync_log_retention_days", 30)

    @property
    def api_health_log_retention_days(self) -> int:
        return self.get("api_health_log_retention_days", 7)

    @property
    def audit_archive_path(self) -> str:
        return self.get("audit_archive_path", "audit_archives")


settings = SettingsService()

__all__ = ["SettingsService", "settings"]
