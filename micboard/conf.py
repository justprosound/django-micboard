"""Centralized configuration access for django-micboard.

.. deprecated::
    This module is a compatibility shim. New code should import ``settings``
    from ``micboard.services.settings`` instead.

    Migration::

        # Old
        from micboard.conf import config

        if config.msp_enabled:
            ...

        # New
        from micboard.services.settings import settings

        if settings.msp_enabled:
            ...
"""

from __future__ import annotations

import warnings
from typing import Any

from micboard.services.settings.settings_service import SettingsService


class MicboardSettingsProxy:
    """Thin compatibility wrapper around :class:`SettingsService`.

    .. deprecated::
        Will be removed after one release cycle. Use
        ``micboard.services.settings.settings`` directly.
    """

    def __init__(self) -> None:
        self._service = SettingsService()

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    @property
    def msp_enabled(self) -> bool:
        return self._service.msp_enabled

    @property
    def multi_site_mode(self) -> bool:
        return self._service.multi_site_mode

    @property
    def site_isolation(self) -> str:
        return self._service.site_isolation

    @property
    def allow_cross_org_view(self) -> bool:
        return self._service.allow_cross_org_view

    @property
    def allow_org_switching(self) -> bool:
        return self._service.allow_org_switching

    @property
    def subdomain_routing(self) -> bool:
        return self._service.subdomain_routing

    @property
    def root_domain(self) -> str:
        return self._service.root_domain

    @property
    def admin_org_selector(self) -> bool:
        return self._service.admin_org_selector

    # ------------------------------------------------------------------
    # Limits and thresholds
    # ------------------------------------------------------------------

    @property
    def global_device_limit(self) -> int | None:
        return self._service.global_device_limit

    @property
    def device_limit_warning_threshold(self) -> float:
        return self._service.device_limit_warning_threshold

    # ------------------------------------------------------------------
    # Audit and retention
    # ------------------------------------------------------------------

    @property
    def activity_log_retention_days(self) -> int:
        return self._service.activity_log_retention_days

    @property
    def service_sync_log_retention_days(self) -> int:
        return self._service.service_sync_log_retention_days

    @property
    def api_health_log_retention_days(self) -> int:
        return self._service.api_health_log_retention_days

    @property
    def audit_archive_path(self) -> str:
        return self._service.audit_archive_path

    # ------------------------------------------------------------------
    # Generic key access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        warnings.warn(
            "micboard.conf.config.get() is deprecated, use "
            "micboard.services.settings.settings.get() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._service.get(key, default)

    def get_config_dict(self) -> dict[str, Any]:
        warnings.warn(
            "micboard.conf.config.get_config_dict() is deprecated, use "
            "micboard.services.settings.settings.get_config_dict() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._service.get_config_dict()

    # ------------------------------------------------------------------
    # Testing flag
    # ------------------------------------------------------------------

    @property
    def testing(self) -> bool:
        return self._service.testing


config = MicboardSettingsProxy()

__all__ = ["config", "MicboardSettingsProxy"]
