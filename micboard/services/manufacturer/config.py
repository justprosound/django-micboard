"""Manufacturer configuration validation and application.

Validates and applies manufacturer-specific configuration settings
using the plugin architecture.
"""

from __future__ import annotations

import logging

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.services.manufacturer.plugin_registry import PluginRegistry

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
                errors.append(f"Plugin health check failed: {health_err!s}")
    except ImportError:
        pass
    except Exception as e:
        errors.append(f"Plugin initialization failed: {e!s}")

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
    except Exception as e:
        logger.error(
            f"Failed to validate configuration for {config.code}: {e}",
            exc_info=True,
            extra={"code": config.code},
        )
        return False
