"""Unified settings access for django-micboard.

Provides a single entry point for all configuration reads across the
codebase, composing Django settings, feature flags, and DB-backed scoped
settings (via SettingsRegistry) into one resolution chain.

Usage::

    from micboard.services.settings import settings

    # Feature flag
    if settings.msp_enabled:
        ...

    # Generic key with fallback
    value = settings.get("SHURE_API_BASE_URL")

    # Scoped DB-backed setting
    value = settings.get("some_key", organization=org)
"""

from __future__ import annotations

from .settings_service import SettingsService, settings

__all__ = ["SettingsService", "settings"]
