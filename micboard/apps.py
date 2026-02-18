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

    # Default configuration (generic app settings, not manufacturer-specific)
    # NOTE: Manufacturer configuration (SHURE_API_*, etc.) is now managed via SettingsRegistry.
    #       Do not add vendor-specific keys here.
    default_config: ClassVar[dict[str, str | int | float | bool | list[int] | None]] = {
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
        # NOTE: Manufacturer-specific config is now resolved via SettingsRegistry, not here.
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

        # Advise about recommended middleware and context processors (do not modify settings)
        self._register_security_middleware()
        self._register_context_processors()

        logger.info("Micboard app initialized (configuration validated)")

    def _register_context_processors(self):
        """Register context processors if not already present."""
        from django.conf import settings

        context_processors = [
            "micboard.context_processors.api_health",
        ]

        # Check if TEMPLATES is configured
        if not hasattr(settings, "TEMPLATES") or not settings.TEMPLATES:
            logger.warning(
                "Project settings has no TEMPLATES configured; Micboard recommends the "
                "following context processors but will not modify your settings automatically."
            )
            return

        # Check each template backend for context processors
        missing_processors = []
        for template_config in settings.TEMPLATES:
            if template_config.get("BACKEND") == "django.template.backends.django.DjangoTemplates":
                current_processors = template_config.get("OPTIONS", {}).get(
                    "context_processors", []
                )
                for processor in context_processors:
                    if processor not in current_processors:
                        missing_processors.append(processor)

        if missing_processors:
            # Remove duplicates
            missing_processors = list(dict.fromkeys(missing_processors))
            logger.info(
                "Micboard recommends adding the following context processors to your "
                "TEMPLATES[0]['OPTIONS']['context_processors']:\n"
                + "\n".join(f"    '{p}'," for p in missing_processors)
            )

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
        # NOTE: Manufacturer-specific config (e.g., SHURE_API_*) is validated via
        #       SettingsRegistry.get() with required=True. Do not hardcode manufacturer
        #       requirements here—this applies only to generic app settings.
        #
        # Generic settings validation (manufacturer-agnostic)
        numeric_settings = [
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

        logger.debug("Micboard configuration validated successfully (manufacturer-agnostic rules)")
