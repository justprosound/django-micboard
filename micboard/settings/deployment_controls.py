"""Dependency-leaf access to host-owned Micboard deployment controls."""

from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings


class DeploymentControls:
    """Read immutable process and tenancy controls from Django host settings."""

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Return one host-owned value without consulting database configuration."""
        return getattr(django_settings, key, default)

    @property
    def multi_site_mode(self) -> bool:
        """Whether Django Site isolation is enabled."""
        return bool(self.get("MICBOARD_MULTI_SITE_MODE", False))

    @property
    def msp_enabled(self) -> bool:
        """Whether organization membership isolation is enabled."""
        return bool(self.get("MICBOARD_MSP_ENABLED", False))

    @property
    def allow_cross_org_view(self) -> bool:
        """Whether platform superusers may view across organizations."""
        return bool(self.get("MICBOARD_ALLOW_CROSS_ORG_VIEW", True))


deployment_controls = DeploymentControls()
