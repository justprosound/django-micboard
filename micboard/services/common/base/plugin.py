from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models.hardware.manufacturer import Manufacturer

    from .client import BaseAPIClient


def get_manufacturer_plugin(code: str) -> type[ManufacturerPlugin]:
    """Return the plugin class for a manufacturer code.

    Attempts to import ``micboard.integrations.<code>.plugin`` and
    locate a concrete ``ManufacturerPlugin`` subclass. Prefers
    ``<CodeTitle>Plugin``, then falls back to another plugin subclass.
    """
    code_str = str(code)
    module_paths = [
        f"micboard.integrations.{code_str}.plugin",
        f"micboard.integrations.{code_str}",
    ]
    mod = None
    for path in module_paths:
        try:
            mod = importlib.import_module(path)
            break
        except ModuleNotFoundError:
            continue

    if mod is None:
        raise ModuleNotFoundError(f"No integration module found for manufacturer '{code_str}'")

    candidate_name = "".join(part.capitalize() for part in code_str.split("_")) + "Plugin"
    if hasattr(mod, candidate_name):
        cls = getattr(mod, candidate_name)
        if isinstance(cls, type) and issubclass(cls, ManufacturerPlugin):
            return cls

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (
            isinstance(obj, type)
            and obj is not ManufacturerPlugin
            and issubclass(obj, ManufacturerPlugin)
        ):
            return obj

    raise ImportError(f"No ManufacturerPlugin subclass found in micboard.integrations.{code_str}")


class BasePlugin(ABC):
    """Docstring."""

    def __init__(self, manufacturer: Manufacturer | None = None) -> None:
        """Docstring."""
        self.manufacturer = manufacturer

    @property
    @abstractmethod
    def name(self) -> str:
        """Docstring."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def code(self) -> str:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def get_devices(self) -> list[dict[str, Any]]:
        """Docstring."""
        raise NotImplementedError()


class ManufacturerPlugin(BasePlugin):
    """Docstring."""

    @abstractmethod
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def get_client(self) -> BaseAPIClient:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def is_healthy(self) -> bool:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def get_discovery_ips(self) -> list[str]:
        """Docstring."""
        raise NotImplementedError()

    @abstractmethod
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Docstring."""
        raise NotImplementedError()
