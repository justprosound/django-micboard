from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Any


def get_manufacturer_plugin(code: str) -> type[ManufacturerPlugin]:
    """Return the plugin class for a manufacturer code.

    Attempts to import ``micboard.integrations.<code>.plugin`` and
    locate the plugin class. Prefers <CodeTitle>Plugin, then falls
    back to classes ending in 'Plugin' or with a ``get_devices`` method.
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
        if isinstance(cls, type):
            return cls

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and attr.endswith("Plugin"):
            return obj

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and hasattr(obj, "get_devices"):
            return obj

    raise ImportError(f"No plugin class found in micboard.integrations.{code_str}")


class BasePlugin(ABC):
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
    @abstractmethod
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError()

    @abstractmethod
    def get_client(self) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError()

    @abstractmethod
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        raise NotImplementedError()

    @abstractmethod
    def is_healthy(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        raise NotImplementedError()
