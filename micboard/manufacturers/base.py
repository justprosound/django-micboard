"""Base classes and abstract plugin API for backwards compatibility.

This module provides minimal abstract base classes expected by code that
previously imported `micboard.manufacturers.base`. New integrations should live
under `micboard.integrations` and implement their own concrete plugin and
client classes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAPIClient(ABC):
    """Minimal API client base used by integration clients (compat shim)."""

    @abstractmethod
    def is_healthy(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        raise NotImplementedError()

    @abstractmethod
    def add_discovery_ips(self, ips: list[str]) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def get_discovery_ips(self) -> list[str]:
        raise NotImplementedError()

    @abstractmethod
    def _make_request(self, *args, **kwargs) -> Any:
        raise NotImplementedError()


class BasePlugin(ABC):
    """Minimal plugin base class — integrations should subclass this or the
    project's more specific ManufacturerPlugin if available.
    """

    def __init__(self, manufacturer: Any | None = None) -> None:
        self.manufacturer = manufacturer

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def code(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def get_devices(self) -> list[dict[str, Any]]:
        raise NotImplementedError()


class ManufacturerPlugin(BasePlugin):
    """Alias kept for older code that imports `ManufacturerPlugin`.

    Integrations may subclass this to satisfy tests and runtime imports.
    """

    @abstractmethod
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError()

    @abstractmethod
    def get_client(self) -> BaseAPIClient:
        raise NotImplementedError()

    pass
