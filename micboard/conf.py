"""Centralized configuration access for django-micboard.

Provides unified interface for accessing Micboard settings, feature flags,
and other configuration values with consistent fallback logic.

Usage:
    from micboard.conf import config

    # Feature flags
    if config.msp_enabled:
        ...

    # Settings registry access
    value = config.get('CUSTOM_KEY', default='...')

    # Or direct access with defaults
    timeout = config.get('SHURE_API_TIMEOUT) or 10
"""

from __future__ import annotations

from django.conf import settings as django_settings


class MicboardSettingsProxy:
    """Centralized access to Micboard configuration."""

    # ========================================================================
    # FEATURE FLAGS (from django.conf.settings)
    # ========================================================================

    @property
    def msp_enabled(self) -> bool:
        """Whether full MSP (Managed Service Provider) mode is enabled."""
        return getattr(django_settings, "MICBOARD_MSP_ENABLED", False)

    @property
    def multi_site_mode(self) -> bool:
        """Whether multi-site mode is enabled (requires django.contrib.sites)."""
        return getattr(django_settings, "MICBOARD_MULTI_SITE_MODE", False)

    @property
    def site_isolation(self) -> str:
        """Site isolation strategy: 'none', 'site', 'organization', or 'campus'."""
        return getattr(django_settings, "MICBOARD_SITE_ISOLATION", "none")

    @property
    def allow_cross_org_view(self) -> bool:
        """Whether superusers can view all organizations in MSP mode."""
        return getattr(django_settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True)

    @property
    def allow_org_switching(self) -> bool:
        """Whether users can switch between organizations."""
        return getattr(django_settings, "MICBOARD_ALLOW_ORG_SWITCHING", True)

    @property
    def subdomain_routing(self) -> bool:
        """Whether subdomain-based organization routing is enabled."""
        return getattr(django_settings, "MICBOARD_SUBDOMAIN_ROUTING", False)

    @property
    def root_domain(self) -> str:
        """Root domain for subdomain routing."""
        return getattr(django_settings, "MICBOARD_ROOT_DOMAIN", "")

    @property
    def admin_org_selector(self) -> bool:
        """Whether to show organization selector in admin navbar."""
        return getattr(django_settings, "MICBOARD_ADMIN_ORG_SELECTOR", True)

    # ========================================================================
    # LIMITS & THRESHOLDS
    # ========================================================================

    @property
    def global_device_limit(self) -> int | None:
        """Global device limit across all organizations."""
        return getattr(django_settings, "MICBOARD_GLOBAL_DEVICE_LIMIT", None)

    @property
    def device_limit_warning_threshold(self) -> float:
        """Device limit warning threshold (0.0-1.0)."""
        return getattr(django_settings, "MICBOARD_DEVICE_LIMIT_WARNING_THRESHOLD", 0.9)

    # ========================================================================
    # AUDIT & RETENTION
    # ========================================================================

    @property
    def activity_log_retention_days(self) -> int:
        """Days to retain activity logs."""
        return getattr(django_settings, "MICBOARD_ACTIVITY_LOG_RETENTION_DAYS", 90)

    @property
    def service_sync_log_retention_days(self) -> int:
        """Days to retain service sync logs."""
        return getattr(django_settings, "MICBOARD_SERVICE_SYNC_LOG_RETENTION_DAYS", 30)

    @property
    def api_health_log_retention_days(self) -> int:
        """Days to retain API health logs."""
        return getattr(django_settings, "MICBOARD_API_HEALTH_LOG_RETENTION_DAYS", 7)

    @property
    def audit_archive_path(self) -> str:
        """Path for audit archive storage."""
        return getattr(django_settings, "MICBOARD_AUDIT_ARCHIVE_PATH", "audit_archives")

    # ========================================================================
    # MICBOARD_CONFIG DICT ACCESS
    # ========================================================================

    @staticmethod
    def get(key: str, default=None):
        """Get a value from MICBOARD_CONFIG dict.

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Value from MICBOARD_CONFIG or default
        """
        config = getattr(django_settings, "MICBOARD_CONFIG", {})
        return config.get(key, default)

    @staticmethod
    def get_config_dict() -> dict:
        """Get entire MICBOARD_CONFIG dictionary.

        Returns:
            MICBOARD_CONFIG dict or empty dict if not configured
        """
        return getattr(django_settings, "MICBOARD_CONFIG", {})

    # ========================================================================
    # TESTING FLAG
    # ========================================================================

    @property
    def testing(self) -> bool:
        """Whether Django is running tests."""
        return getattr(django_settings, "TESTING", False)


config = MicboardSettingsProxy()

__all__ = ["config", "MicboardSettingsProxy"]
