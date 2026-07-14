"""Feature-flag helpers for optional multi-tenancy deployments."""

from __future__ import annotations


def is_msp_enabled() -> bool:
    """Check if MSP features are enabled."""
    try:
        from django.conf import settings

        return getattr(settings, "MICBOARD_MSP_ENABLED", False)
    except Exception:
        return False


def is_multisite_enabled() -> bool:
    """Check if multi-site mode is enabled."""
    try:
        from django.conf import settings

        return getattr(settings, "MICBOARD_MULTI_SITE_MODE", False)
    except Exception:
        return False


__all__ = ["is_msp_enabled", "is_multisite_enabled"]
