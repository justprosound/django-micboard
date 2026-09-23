from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    from .client import BaseAPIClient

RealtimeTransport = Literal["sse", "websocket"]


_plugin_cache: dict[str, type[ManufacturerPlugin]] = {}


def clear_plugin_cache() -> None:
    """Forget resolved plugin classes, so a test starts from a cold cache."""
    _plugin_cache.clear()


def build_manufacturer_plugin(manufacturer: Manufacturer) -> ManufacturerPlugin:
    """Return a plugin bound to ``manufacturer``.

    This is the one way to obtain a plugin. It raises when a manufacturer has no shipped
    integration, so every caller sees the same failure rather than a ``None`` some branch on
    and others do not.
    """
    plugin_class = get_manufacturer_plugin(manufacturer.code)
    return plugin_class(manufacturer)


def get_manufacturer_plugin(code: str) -> type[ManufacturerPlugin]:
    """Return the plugin class for a manufacturer code, resolving it at most once.

    Attempts to import ``micboard.integrations.<code>.plugin`` and
    locate a concrete ``ManufacturerPlugin`` subclass. Prefers
    ``<CodeTitle>Plugin``, then falls back to another plugin subclass.
    """
    code_str = str(code)
    cached = _plugin_cache.get(code_str)
    if cached is not None:
        return cached
    module_paths = [
        f"micboard.integrations.{code_str}.plugin",
        f"micboard.integrations.{code_str}",
    ]
    mod = None
    for path in module_paths:
        try:
            mod = importlib.import_module(path)
            break
        except ModuleNotFoundError as exc:
            # Only a missing integration module means "try the next path". A
            # ModuleNotFoundError raised inside a shipped plugin — a vendor dependency that
            # is not installed — must escape, or callers report "Plugin not found" for what
            # is really an initialization failure.
            missing = exc.name
            if missing is not None and missing != path and not path.startswith(f"{missing}."):
                raise
            continue

    if mod is None:
        raise ModuleNotFoundError(f"No integration module found for manufacturer '{code_str}'")

    candidate_name = "".join(part.capitalize() for part in code_str.split("_")) + "Plugin"
    if hasattr(mod, candidate_name):
        cls = getattr(mod, candidate_name)
        if isinstance(cls, type) and issubclass(cls, ManufacturerPlugin):
            _plugin_cache[code_str] = cls
            return cls

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (
            isinstance(obj, type)
            and obj is not ManufacturerPlugin
            and issubclass(obj, ManufacturerPlugin)
        ):
            _plugin_cache[code_str] = obj
            return obj

    raise ImportError(f"No ManufacturerPlugin subclass found in micboard.integrations.{code_str}")


class BasePlugin(ABC):
    """Base interface for all manufacturer plugins."""

    def __init__(self, manufacturer: Manufacturer | None = None) -> None:
        """Initialize the plugin, optionally binding it to a specific manufacturer instance."""
        self.manufacturer = manufacturer

    @property
    @abstractmethod
    def name(self) -> str:
        """The human-readable name of the plugin."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def code(self) -> str:
        """The unique string identifier or code for the plugin."""
        raise NotImplementedError()

    @abstractmethod
    def get_devices(self) -> list[dict[str, Any]]:
        """Retrieve a list of all devices associated with or discovered by this plugin."""
        raise NotImplementedError()


class ManufacturerPlugin(BasePlugin):
    """Extended plugin interface specifically for manufacturer hardware integrations."""

    @property
    @abstractmethod
    def realtime_transport(self) -> RealtimeTransport | None:
        """The transport this integration streams over, or ``None`` when it has no stream.

        The shared subscription runner reads this rather than mapping manufacturer codes to
        transports, so no orchestration code needs to know a vendor by name.
        """
        raise NotImplementedError()

    @abstractmethod
    async def subscribe_to_chassis(
        self,
        chassis: WirelessChassis,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Open this integration's stream for one chassis and await its updates.

        The integration owns connection setup, authentication, framing, and cleanup; the
        runner owns leasing, inventory selection, connection tracking, and persistence.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Retrieve all channels associated with a specific device identifier."""
        raise NotImplementedError()

    @abstractmethod
    def get_client(self) -> BaseAPIClient:
        """Get an instance of the configured API client for this manufacturer."""
        raise NotImplementedError()

    @abstractmethod
    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Transform raw API device data into the standardized application format."""
        raise NotImplementedError()

    @abstractmethod
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Fetch details for a single device by its identifier."""
        raise NotImplementedError()

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if the plugin and its underlying integrations are currently healthy."""
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Perform a detailed health check and return the results as a dictionary."""
        raise NotImplementedError()

    @abstractmethod
    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add a list of IP addresses to the plugin's discovery targets."""
        raise NotImplementedError()

    @abstractmethod
    def get_discovery_ips(self) -> list[str]:
        """Retrieve the list of currently configured discovery IP addresses."""
        raise NotImplementedError()

    @abstractmethod
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove a list of IP addresses from the plugin's discovery targets."""
        raise NotImplementedError()
