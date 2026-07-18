"""Unified settings resolution service.

Composes Django settings, feature flags, package defaults, and the
DB-backed SettingsRegistry into a single resolution chain.
"""

from __future__ import annotations

from typing import Any

from micboard.services.settings.registry import SettingsRegistry
from micboard.settings.defaults import DEFAULT_CONFIG
from micboard.settings.deployment_controls import deployment_controls

_NOT_FOUND = object()


class SettingsService:
    """Unified settings resolution with multi-source fallback.

    Resolution order for ``get()``:

    1. Deployment controls mapped to immutable Django ``MICBOARD_*`` settings
    2. DB Setting with scope (org/site/manufacturer) via ``SettingsRegistry``
    3. ``settings.MICBOARD_CONFIG`` dict key
    4. Package defaults (``POLL_INTERVAL``, etc.)
    5. Registered ``SettingDefinition`` default
    6. Provided *default*
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
        self._registry = SettingsRegistry

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
        if key.startswith("MICBOARD_"):
            return deployment_controls.get(key, default)

        flag_name = self._FEATURE_FLAG_KEYS.get(key)
        if flag_name is not None:
            return deployment_controls.get(flag_name, default)

        value = self._registry.get(
            key,
            default=None,
            organization=organization,
            site=site,
            manufacturer=manufacturer,
            include_definition_default=False,
        )
        if value is not None:
            return value

        micboard_config = deployment_controls.get("MICBOARD_CONFIG", {})
        if key in micboard_config:
            return micboard_config[key]

        if key in DEFAULT_CONFIG:
            return DEFAULT_CONFIG[key]

        definition_default = self._registry.get_definition_default(key, default=_NOT_FOUND)
        if definition_default is not _NOT_FOUND:
            return definition_default

        return default

    def get_config_dict(self) -> dict[str, Any]:
        """Return ``MICBOARD_CONFIG`` merged with package defaults."""
        micboard_config = deployment_controls.get("MICBOARD_CONFIG", {})
        return {**DEFAULT_CONFIG, **micboard_config}

    def invalidate_value_cache(self, key: str | None = None) -> None:
        """Invalidate one resolved database value or every cached value."""
        self._registry.invalidate_cache(key)

    def invalidate_definition_cache(self, key: str | None = None) -> None:
        """Invalidate definition metadata and every value derived from it."""
        self._registry.invalidate_definition(key)

    # ------------------------------------------------------------------
    # Feature-flag convenience properties
    # ------------------------------------------------------------------

    @property
    def msp_enabled(self) -> bool:
        return bool(self.get("msp_enabled", False))

    @property
    def multi_site_mode(self) -> bool:
        return bool(self.get("multi_site_mode", False))

    @property
    def site_isolation(self) -> str:
        return str(self.get("site_isolation", "none"))

    @property
    def allow_cross_org_view(self) -> bool:
        return bool(self.get("allow_cross_org_view", True))

    @property
    def allow_org_switching(self) -> bool:
        return bool(self.get("allow_org_switching", True))

    @property
    def subdomain_routing(self) -> bool:
        return bool(self.get("subdomain_routing", False))

    @property
    def root_domain(self) -> str:
        return str(self.get("root_domain", ""))

    @property
    def admin_org_selector(self) -> bool:
        return bool(self.get("admin_org_selector", True))

    @property
    def global_device_limit(self) -> int | None:
        val = self.get("global_device_limit", None)
        return int(val) if val not in (None, "") else None

    @property
    def device_limit_warning_threshold(self) -> float:
        val = self.get("device_limit_warning_threshold", 0.9)
        return float(val) if val not in (None, "") else 0.9

    @property
    def activity_log_retention_days(self) -> int:
        val = self.get("activity_log_retention_days", 90)
        return int(val) if val not in (None, "") else 90

    @property
    def service_sync_log_retention_days(self) -> int:
        val = self.get("service_sync_log_retention_days", 30)
        return int(val) if val not in (None, "") else 30

    @property
    def api_health_log_retention_days(self) -> int:
        val = self.get("api_health_log_retention_days", 7)
        return int(val) if val not in (None, "") else 7

    @property
    def audit_archive_path(self) -> str:
        return str(self.get("audit_archive_path", "audit_archives"))


settings = SettingsService()

__all__ = ["SettingsService", "settings"]
