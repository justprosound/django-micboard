"""
Manufacturer plugin system for django-micboard.

This package provides a plugin architecture for supporting multiple wireless
microphone manufacturers in the micboard system.
"""

from __future__ import annotations

import importlib
import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class ManufacturerPlugin(ABC):
    """Abstract base class for manufacturer plugins."""

    def __init__(self, manufacturer: Manufacturer):
        self.manufacturer = manufacturer
        self.config = manufacturer.config

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the manufacturer."""
        pass

    @property
    @abstractmethod
    def code(self) -> str:
        """Short code identifier for the manufacturer."""
        pass

    @abstractmethod
    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from the manufacturer's API."""
        pass

    @abstractmethod
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        pass

    @abstractmethod
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        pass

    @abstractmethod
    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Transform manufacturer API data to micboard format."""
        pass

    @abstractmethod
    def transform_transmitter_data(
        self, tx_data: dict[str, Any], channel_num: int
    ) -> dict[str, Any] | None:
        """Transform transmitter data from manufacturer format to micboard format."""
        pass

    def get_device_identity(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device identity info if available."""
        return None

    def get_device_network(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device network info if available."""
        return None

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device status info if available."""
        return None

    def connect_and_subscribe(self, device_id: str, callback: Callable[[dict[str, Any]], None]):
        """Establish WebSocket connection and subscribe to device updates."""
        raise NotImplementedError("WebSocket support not implemented for this manufacturer")

    def is_healthy(self) -> bool:
        """Check if the manufacturer plugin is healthy."""
        return True

    def check_health(self) -> dict[str, Any]:
        """Perform health check and return status."""
        return {
            "status": "healthy" if self.is_healthy() else "unhealthy",
            "manufacturer": self.name,
        }


def get_manufacturer_plugin(manufacturer_code: str) -> type[ManufacturerPlugin]:
    """Get the plugin class for a manufacturer."""
    try:
        module = importlib.import_module(f"micboard.manufacturers.{manufacturer_code}")
        plugin_class = getattr(module, f"{manufacturer_code.capitalize()}Plugin")
        return cast(type[ManufacturerPlugin], plugin_class)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to load plugin for manufacturer '{manufacturer_code}': {e}")
        raise ValueError(f"Manufacturer plugin '{manufacturer_code}' not found") from e


def get_available_manufacturers() -> list[str]:
    """Get list of available manufacturer codes by scanning the manufacturers directory."""
    manufacturers_dir = os.path.dirname(__file__)
    manufacturers = []

    for item in os.listdir(manufacturers_dir):
        if os.path.isdir(os.path.join(manufacturers_dir, item)) and not item.startswith("__"):
            # Check if the plugin module exists and has the expected plugin class
            try:
                module = importlib.import_module(f"micboard.manufacturers.{item}")
                plugin_class = getattr(module, f"{item.capitalize()}Plugin")
                if issubclass(plugin_class, ManufacturerPlugin):
                    manufacturers.append(item)
            except (ImportError, AttributeError):
                # Skip directories that don't contain valid plugins
                continue

    return sorted(manufacturers)


__all__ = [
    "ManufacturerPlugin",
    "get_available_manufacturers",
    "get_manufacturer_plugin",
]
