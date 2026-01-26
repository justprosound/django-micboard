"""Optional multi-tenancy module for MSP deployments.

This module provides Organization and Campus models for multi-tenant
deployments. It only loads when MICBOARD_MSP_ENABLED = True in settings.

For single-site deployments, stub implementations are provided that
maintain API compatibility without adding overhead.
"""

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


# Conditional imports - only try if settings available
def _load_models():
    """Lazy load models when needed."""
    if is_msp_enabled():
        try:
            from .models import Campus, Organization, OrganizationMembership

            return Organization, Campus, OrganizationMembership
        except ImportError:
            # Models not yet migrated
            return None, None, None
    return None, None, None


# Export functions and lazy-load models when accessed
__all__ = ["is_msp_enabled", "is_multisite_enabled"]
