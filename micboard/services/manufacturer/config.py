"""Manufacturer configuration validation and application.

Validates and applies manufacturer-specific configuration settings
using the plugin architecture.
"""

from __future__ import annotations

import logging

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.services.manufacturer.plugin_registry import PluginRegistry
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

REQUIRED_FIELDS_MAP: dict[str, list[str]] = {
    "shure": ["SHURE_API_BASE_URL", "SHURE_API_SHARED_KEY"],
    "sennheiser": ["SENNHEISER_API_BASE_URL"],
}


def validate_manufacturer_config(
    *,
    config: ManufacturerConfiguration,
) -> dict[str, bool | list[str]]:
    """Validate a manufacturer configuration.

    Returns dict with keys:
    - is_valid: bool
    - errors: list of error messages

    Does NOT mutate the config instance — caller must persist results.
    """
    errors: list[str] = []

    try:
        plugin = PluginRegistry.get_plugin(config.code)
        if not plugin:
            errors.append(f"Plugin not found or not enabled: {config.code}")
        else:
            try:
                client = plugin.get_client()
                if not client:
                    errors.append(f"Plugin client initialization failed for {config.code}")
            except Exception as health_err:
                logger.exception(
                    "Manufacturer plugin health check failed for %s",
                    config.code,
                    exc_info=sanitized_exception_info(health_err),
                )
                errors.append(
                    f"Plugin health check failed ({type(health_err).__name__}); details redacted."
                )
    except ImportError as exc:
        logger.exception(
            "Manufacturer plugin import failed for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
        )
        errors.append(f"Plugin import failed for {config.code}")
    except Exception as exc:
        logger.exception(
            "Manufacturer plugin initialization failed for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
        )
        errors.append(f"Plugin initialization failed ({type(exc).__name__}); details redacted.")

    required_fields = REQUIRED_FIELDS_MAP.get(config.code, [])
    for field in required_fields:
        if field not in config.config:
            errors.append(f"Missing required configuration: {field}")

    if errors:
        logger.warning(
            f"Configuration validation failed for {config.code}",
            extra={"code": config.code, "errors": errors},
        )
    else:
        logger.info(
            f"Configuration validated successfully for {config.code}",
            extra={"code": config.code},
        )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
    }


def apply_manufacturer_config(
    *,
    config: ManufacturerConfiguration,
) -> bool:
    """Validate and log intent to apply a manufacturer configuration.

    Returns True if config is valid and can be applied, False otherwise.
    """
    try:
        if not config.is_valid:
            logger.warning(
                f"Cannot apply invalid configuration for {config.code}",
                extra={"code": config.code},
            )
            return False

        logger.info(
            f"Configuration validated for {config.code}. "
            f"Will be applied on next plugin initialization.",
            extra={"code": config.code},
        )
        return True
    except Exception as exc:
        logger.exception(
            "Failed to validate configuration for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
            extra={"code": config.code},
        )
        return False
