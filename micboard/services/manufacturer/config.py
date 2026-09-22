"""Manufacturer configuration validation and application.

Validates and applies manufacturer-specific configuration settings
using the plugin architecture.
"""

from __future__ import annotations

import logging

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.common.base.plugin import build_manufacturer_plugin
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

REQUIRED_FIELDS_MAP: dict[str, list[str]] = {
    "shure": ["SHURE_API_BASE_URL", "SHURE_API_SHARED_KEY"],
    "sennheiser": ["SENNHEISER_API_BASE_URL"],
}


def _probe_manufacturer_plugin(config: ManufacturerConfiguration) -> list[str]:
    """Return the errors found while building this code's plugin and reaching its client."""
    manufacturer = Manufacturer.objects.filter(code=config.code).first()
    if manufacturer is None:
        return [f"No manufacturer registered for code: {config.code}"]

    try:
        plugin = build_manufacturer_plugin(manufacturer)
    except (ImportError, ValueError) as exc:
        logger.warning(
            "Manufacturer plugin could not be built for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
        )
        return [f"Plugin not found or not enabled: {config.code}"]
    except Exception as exc:
        logger.exception(
            "Manufacturer plugin initialization failed for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
        )
        return [f"Plugin initialization failed ({type(exc).__name__}); details redacted."]

    try:
        client = plugin.get_client()
    except Exception as exc:
        logger.exception(
            "Manufacturer plugin health check failed for %s",
            config.code,
            exc_info=sanitized_exception_info(exc),
        )
        return [f"Plugin health check failed ({type(exc).__name__}); details redacted."]

    if not client:
        return [f"Plugin client initialization failed for {config.code}"]
    return []


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
    errors: list[str] = _probe_manufacturer_plugin(config)

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
