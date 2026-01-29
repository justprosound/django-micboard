"""Django application configuration for Micboard.

This module defines the AppConfig for the Micboard reusable app, including
default settings, signal registration, and startup configuration validation.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class MicboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "micboard"
    verbose_name = "Micboard - Wireless Hardware Monitoring"

    # Store resolved configuration (merged defaults + user settings)
    _resolved_config: ClassVar[dict[str, Any] | None] = None

    # Default configuration
    default_config: ClassVar[dict[str, str | int | float | bool | list[int] | None]] = {
        "SHURE_API_BASE_URL": "http://localhost:8080",
        "SHURE_API_SHARED_KEY": None,
        "SHURE_API_TIMEOUT": 10,
        "SHURE_API_VERIFY_SSL": True,
        "SHURE_API_MAX_RETRIES": 3,
        "SHURE_API_RETRY_BACKOFF": 0.5,
        "SHURE_API_RETRY_STATUS_CODES": [429, 500, 502, 503, 504],
        "POLL_INTERVAL": 5,
        "CACHE_TIMEOUT": 30,
        "TRANSMITTER_INACTIVITY_SECONDS": 10,
    }

    @classmethod
    def get_config(cls) -> dict[str, Any]:
        """Get resolved configuration (merged defaults + user settings).

        Returns:
            Merged configuration dictionary.

        Raises:
            RuntimeError: If configuration not yet initialized (Django apps not loaded).
        """
        if cls._resolved_config is None:
            raise RuntimeError(
                "Micboard configuration not yet initialized. "
                "Ensure Django apps are loaded before accessing config."
            )
        return cls._resolved_config

    def ready(self):
        """Initialize app when Django starts."""
        from django.conf import settings

        # Merge user config with defaults without mutating settings
        user_config = getattr(settings, "MICBOARD_CONFIG", {})
        self._resolved_config = {**self.default_config, **user_config}

        # Validate merged configuration
        self._validate_configuration(self._resolved_config)

        # Register system checks
        from django.core.checks import Tags, register

        from micboard.checks import check_micboard_configuration

        register(check_micboard_configuration, Tags.compatibility)

        # Import health checks to trigger registration if django-health-check is present
        try:
            import micboard.checks  # noqa
        except ImportError:
            logger.debug("django-health-check not installed, skipping health check registration")

        # Advise about recommended middleware (do not modify settings)
        self._register_security_middleware()

        logger.info("Micboard app initialized (configuration validated)")

    def _register_security_middleware(self):
        """Register security middleware if not already present."""
        from django.conf import settings

        middleware_classes = [
            "micboard.middleware.SecurityHeadersMiddleware",
            "micboard.middleware.RequestLoggingMiddleware",
        ]

        if not hasattr(settings, "MIDDLEWARE"):
            logger.warning(
                "Project settings has no MIDDLEWARE configured; Micboard recommends the "
                "following middleware but will not modify your settings automatically."
            )

        missing = [
            m
            for m in middleware_classes
            if not hasattr(settings, "MIDDLEWARE") or m not in settings.MIDDLEWARE
        ]
        if missing:
            logger.info(
                "Micboard recommends adding the following middleware to your project "
                "settings.MIDDLEWARE:\n" + "\n".join(f"    {m}" for m in missing)
            )

    def _validate_configuration(self, config: dict[str, Any]):
        """Validate merged configuration.

        Args:
            config: Merged configuration dictionary to validate.

        Raises:
            ImproperlyConfigured: If configuration is invalid.
        """
        # Validate required URL
        base_url = config.get("SHURE_API_BASE_URL")
        if not base_url:
            raise ImproperlyConfigured(
                "MICBOARD_CONFIG['SHURE_API_BASE_URL'] is required. "
                "Please set it in your settings.py"
            )

        # Validate numeric settings
        numeric_settings = [
            "SHURE_API_TIMEOUT",
            "SHURE_API_MAX_RETRIES",
            "POLL_INTERVAL",
            "CACHE_TIMEOUT",
            "TRANSMITTER_INACTIVITY_SECONDS",
        ]
        for key in numeric_settings:
            value = config.get(key)
            if value is not None and not isinstance(value, (int, float)):
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be a number, got {type(value).__name__}"
                )
            if value is not None and value <= 0:
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be positive, got {value}"
                )

        logger.debug("Micboard configuration validated successfully")
