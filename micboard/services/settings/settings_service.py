"""Unified settings resolution service.

Composes Django settings, feature flags, AppConfig defaults, and the
DB-backed SettingsRegistry into a single resolution chain.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings as django_settings

from micboard.apps import MicboardConfig
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
