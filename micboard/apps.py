"""Django application configuration for Micboard.

This module defines the AppConfig for the Micboard reusable app, including
default settings, signal registration, and startup configuration validation.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class MicboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "micboard"
    verbose_name = "Micboard - Wireless Hardware Monitoring"

    def ready(self) -> None:
        """Initialize app when Django starts."""
        from micboard.services.settings.settings_service import settings as micboard_settings

        # Resolve configuration through the app's single settings seam.
        resolved_config = micboard_settings.get_config_dict()

        # Validate merged configuration
        self._validate_configuration(resolved_config)

        from micboard.model_lifecycle import register_model_lifecycle

        register_model_lifecycle()

        # Register system checks
        from django.core.checks import Tags, register

        from micboard.checks import check_micboard_configuration

        register(check_micboard_configuration, Tags.compatibility)

        # Advise about recommended middleware and context processors (do not modify settings)
        self._recommend_security_middleware()
        self._recommend_context_processors()
        self._register_background_tasks()

        logger.info("Micboard app initialized (configuration validated)")

    def _register_background_tasks(self) -> None:
        """Register task entry points on the host project's native Huey queue."""
        from micboard.utils.dependencies import huey_is_configured, register_huey_task

        if not huey_is_configured():
            return

        from micboard.tasks.maintenance.charger import poll_charger_data
        from micboard.tasks.monitoring.health import (
            check_manufacturer_api_health,
            check_realtime_connection_health,
            check_selected_api_server_connections,
        )
        from micboard.tasks.monitoring.sse import start_sse_subscriptions
        from micboard.tasks.monitoring.websocket import start_shure_websocket_subscriptions
        from micboard.tasks.sync.discovery import (
            cache_all_discovery_candidates,
            run_discovery_sync_task,
            run_manufacturer_discovery_task,
        )
        from micboard.tasks.sync.polling import (
            poll_api_server_device,
            poll_manufacturer_devices,
            refresh_selected_chassis,
        )

        task_functions = (
            poll_charger_data,
            check_manufacturer_api_health,
            check_realtime_connection_health,
            check_selected_api_server_connections,
            start_sse_subscriptions,
            start_shure_websocket_subscriptions,
            cache_all_discovery_candidates,
            run_discovery_sync_task,
            run_manufacturer_discovery_task,
            poll_api_server_device,
            poll_manufacturer_devices,
            refresh_selected_chassis,
        )
        for task_function in task_functions:
            register_huey_task(task_function)

    def _recommend_context_processors(self) -> None:
        """Report context processors the host has not configured."""
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
            if not isinstance(template_config, dict):
                continue
            if template_config.get("BACKEND") == "django.template.backends.django.DjangoTemplates":
                options = template_config.get("OPTIONS", {})
                if not isinstance(options, dict):
                    continue
                current_processors = options.get("context_processors", [])
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

    def _recommend_security_middleware(self) -> None:
        """Report built-in security middleware the host has not configured."""
        from django.conf import settings

        middleware_classes = ["django.middleware.security.SecurityMiddleware"]

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

    def _validate_configuration(self, config: dict[str, Any]) -> Any:
        """Validate merged configuration.

        Args:
            config: Merged configuration dictionary to validate.

        Raises:
            ImproperlyConfigured: If configuration is invalid.
        """
        # Manufacturer-specific values are validated by their setting definitions and
        # persistence DTOs. Keep startup validation limited to generic host configuration.
        #
        # Generic settings validation (manufacturer-agnostic)
        numeric_settings = [
            "POLL_INTERVAL",
            "CACHE_TIMEOUT",
            "TRANSMITTER_INACTIVITY_SECONDS",
        ]
        for key in numeric_settings:
            value = config.get(key)
            if value is not None and not isinstance(value, int | float):
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be a number, got {type(value).__name__}"
                )
            if value is not None and value <= 0:
                raise ImproperlyConfigured(
                    f"MICBOARD_CONFIG['{key}'] must be positive, got {value}"
                )

        logger.debug("Micboard configuration validated successfully (manufacturer-agnostic rules)")
