"""
Django application configuration for Micboard.

This module defines the AppConfig for the Micboard reusable app, including
default settings, signal registration, and startup configuration validation.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class MicboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "micboard"
    verbose_name = "Micboard - Shure Wireless Monitoring"

    # Default configuration
    default_config: ClassVar[dict[str, str | int | float | bool | list[int] | None]] = {
        "SHURE_API_BASE_URL": "http://localhost:8080",
        "SHURE_API_USERNAME": None,
        "SHURE_API_PASSWORD": None,
        "SHURE_API_TIMEOUT": 10,
        "SHURE_API_VERIFY_SSL": True,
        "SHURE_API_MAX_RETRIES": 3,
        "SHURE_API_RETRY_BACKOFF": 0.5,
        "SHURE_API_RETRY_STATUS_CODES": [429, 500, 502, 503, 504],
        "POLL_INTERVAL": 5,
        "CACHE_TIMEOUT": 30,
        "TRANSMITTER_INACTIVITY_SECONDS": 10,
    }

    def ready(self):
        """Initialize app when Django starts"""
        # Validate configuration
        self._validate_configuration()

        # Import signals to register them
        from . import signals  # noqa: F401

        # Register security middleware
        self._register_security_middleware()

        logger.info("Micboard app initialized")

    def _register_security_middleware(self):
        """Register security middleware if not already present"""
        from django.conf import settings

        middleware_classes = [
            "micboard.middleware.SecurityHeadersMiddleware",
            "micboard.middleware.RequestLoggingMiddleware",
        ]

        if not hasattr(settings, "MIDDLEWARE"):
            settings.MIDDLEWARE = []

        for middleware in middleware_classes:
            if middleware not in settings.MIDDLEWARE:
                settings.MIDDLEWARE.append(middleware)
                logger.debug(f"Registered security middleware: {middleware}")

    def _validate_configuration(self):
        """Validate MICBOARD_CONFIG settings"""
        config = getattr(settings, "MICBOARD_CONFIG", {})

        # Merge with defaults
        merged_config = {**self.default_config, **config}

        # Validate required URL
        base_url = merged_config.get("SHURE_API_BASE_URL")
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
            value = merged_config.get(key)
            if value is not None and not isinstance(value, (int, float)):
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be a number, got {type(value).__name__}"
                )
            if value is not None and value <= 0:
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be positive, got {value}"
                )

        # Apply merged config back to settings for consistency
        settings.MICBOARD_CONFIG = merged_config

        logger.debug("Micboard configuration validated successfully")
