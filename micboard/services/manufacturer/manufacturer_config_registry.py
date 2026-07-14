"""Manufacturer configuration registry using SettingsRegistry."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from micboard.services.shared.settings_registry import SettingsRegistry

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)


@dataclass
class ManufacturerConfig:
    """Configuration for a specific manufacturer."""

    manufacturer_code: str
    status_constants: dict[str, str] = field(default_factory=dict)
    battery_thresholds: dict[str, int] = field(default_factory=dict)
    device_roles: list[str] = field(default_factory=list)
    metadata_schema: dict[str, Any] = field(default_factory=dict)
    health_check_interval: int = 300  # seconds
    api_timeout: int = 30  # seconds
    max_devices_per_request: int = 100
    supports_discovery_ips: bool = True
    supports_health_check: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "manufacturer_code": self.manufacturer_code,
            "status_constants": self.status_constants,
            "battery_thresholds": self.battery_thresholds,
            "device_roles": self.device_roles,
            "metadata_schema": self.metadata_schema,
            "health_check_interval": self.health_check_interval,
            "api_timeout": self.api_timeout,
            "max_devices_per_request": self.max_devices_per_request,
            "supports_discovery_ips": self.supports_discovery_ips,
            "supports_health_check": self.supports_health_check,
        }


class ManufacturerConfigRegistry:
    """Registry for manufacturer-specific configurations."""

    _registry: dict[str, ManufacturerConfig] = {}
    _defaults: dict[str, ManufacturerConfig] = {}

    @classmethod
    def register_defaults(cls, manufacturer_code: str, config: ManufacturerConfig) -> None:
        """Register default configuration for a manufacturer."""
        cls._defaults[manufacturer_code] = config
        # Initialize registry with defaults
        cls._registry[manufacturer_code] = config

    @classmethod
    def get(
        cls,
        manufacturer_code: str,
        manufacturer: Manufacturer | None = None,
    ) -> ManufacturerConfig:
        """Get manufacturer configuration with database overrides.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure')
            manufacturer: Manufacturer instance for database lookups

        Returns:
            ManufacturerConfig with database overrides applied
        """
        # Start with defaults or registry
        registered_config = cls._registry.get(manufacturer_code)
        if not registered_config:
            logger.warning("No configuration found for manufacturer %s", manufacturer_code)
            return ManufacturerConfig(manufacturer_code=manufacturer_code)
        config = deepcopy(registered_config)

        # If no manufacturer instance, return registry version
        if not manufacturer:
            return config

        # Load overrides from SettingsRegistry
        overrides = SettingsRegistry.get_all_for_scope(manufacturer=manufacturer)

        # Apply overrides to config
        if overrides:
            config = cls._apply_overrides(config, overrides)

        return config

    @classmethod
    def set_override(
        cls,
        manufacturer_code: str,
        key: str,
        value: Any,
        manufacturer: Manufacturer | None = None,
    ) -> None:
        """Set a configuration override for a manufacturer.

        Args:
            manufacturer_code: Manufacturer code
            key: Configuration key (e.g., 'battery_low_threshold')
            value: Value to set
            manufacturer: Manufacturer instance (for scope)
        """
        SettingsRegistry.set(
            key,
            value,
            manufacturer=manufacturer,
        )
        logger.info("Set manufacturer override %s.%s", manufacturer_code, key)

    @classmethod
    def _apply_overrides(
        cls,
        config: ManufacturerConfig,
        overrides: dict[str, Any],
    ) -> ManufacturerConfig:
        """Apply database overrides to config."""
        direct_fields = {
            "health_check_interval": "health_check_interval",
            "api_timeout": "api_timeout",
            "device_max_requests_per_call": "max_devices_per_request",
            "supports_discovery_ips": "supports_discovery_ips",
            "supports_health_check": "supports_health_check",
        }
        battery_fields = {
            "battery_good_level": "good",
            "battery_low_level": "low",
            "battery_critical_level": "critical",
        }
        for key, value in overrides.items():
            if field_name := direct_fields.get(key):
                setattr(config, field_name, value)
            elif threshold_name := battery_fields.get(key):
                config.battery_thresholds[threshold_name] = value

        return config

    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialize default manufacturer configurations."""
        # Shure defaults
        shure_config = ManufacturerConfig(
            manufacturer_code="shure",
            status_constants={
                "DISCOVERED": "discovered",
                "ONLINE": "online",
                "OFFLINE": "offline",
                "INCOMPATIBLE": "incompatible",
            },
            battery_thresholds={
                "good": 90,
                "low": 20,
                "critical": 0,
            },
            device_roles=["receiver", "transmitter", "bodypack", "headset"],
            metadata_schema={
                "compatibility": str,
                "deviceState": str,
                "communicationProtocol": dict,
            },
            health_check_interval=300,
            api_timeout=30,
            supports_discovery_ips=True,
            supports_health_check=True,
        )
        cls.register_defaults("shure", shure_config)

        # Sennheiser defaults
        sennheiser_config = ManufacturerConfig(
            manufacturer_code="sennheiser",
            status_constants={
                "DISCOVERED": "discovered",
                "ONLINE": "online",
                "OFFLINE": "offline",
                "ERROR": "error",
            },
            battery_thresholds={
                "good": 85,
                "low": 25,
                "critical": 5,
            },
            device_roles=["transmitter", "receiver"],
            metadata_schema={
                "state": str,
                "hardware_version": str,
                "software_version": str,
            },
            health_check_interval=300,
            api_timeout=60,
            supports_discovery_ips=True,
            supports_health_check=True,
        )
        cls.register_defaults("sennheiser", sennheiser_config)


# Initialize on module load
ManufacturerConfigRegistry.initialize_defaults()
