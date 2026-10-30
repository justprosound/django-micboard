import logging
from typing import Any, cast

from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.inventory import DeviceInventory
from micboard.services.common.base.rate_limiter import rate_limit

from .exceptions import ShureAPIError

logger = logging.getLogger(__name__)


class ShureDeviceClient:
    """Client for interacting with Shure System API for device data."""

    def __init__(self, api_client: BaseAPIClient) -> None:
        """Create a device client bound to the parent API client."""
        self.api_client = api_client

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> DeviceInventory:
        """Get list of all devices from Shure System API.

        Returns:
            List of device node dictionaries with normalized structure.
            Extracts deviceId from hardwareIdentity to top-level id field.
        """
        result = self.api_client._make_request("GET", "/api/v1/devices")
        devices, complete = self._device_nodes(result)
        normalized = DeviceInventory(complete=complete)
        for device in devices:
            if not isinstance(device, dict):
                normalized.complete = False
                continue
            if not self._lift_identity_fields(device):
                normalized.complete = False
            normalized.append(device)
        return normalized

    @staticmethod
    def _device_nodes(result: Any) -> tuple[list[Any], bool]:
        """Return the raw device items of a response and whether none had to be dropped."""
        if isinstance(result, dict) and "edges" in result:
            # GraphQL-style response with edges/nodes
            edges = result.get("edges", [])
            nodes = [edge["node"] for edge in edges if isinstance(edge, dict) and "node" in edge]
            return nodes, len(nodes) == len(edges)
        if isinstance(result, list):
            # Fallback for direct list response
            return result, True
        # An empty response is a known empty answer; any other shape is unreadable.
        return [], result is None

    @staticmethod
    def _lift_identity_fields(device: dict[str, Any]) -> bool:
        """Copy nested identity fields to the top level; False when the device has no id."""
        hardware_identity = device.get("hardwareIdentity", {})
        device_id = hardware_identity.get("deviceId")
        if device_id:
            # Add top-level id field expected by transformers
            device["id"] = device_id
        if "serialNumber" in hardware_identity:
            device.setdefault("serialNumber", hardware_identity["serialNumber"])
        communication = device.get("communicationProtocol", {})
        if "address" in communication:
            device.setdefault("ipAddress", communication["address"])
        software = device.get("softwareIdentity", {})
        if "model" in software:
            device.setdefault("model", software["model"])
        if "firmwareVersion" in software:
            device.setdefault("firmwareVersion", software["firmwareVersion"])
        return bool(device_id)

    @rate_limit(calls_per_second=5.0)
    def get_supported_device_models(self) -> list[str]:
        """Fetch the list of supported device models from Shure System API.

        Returns:
            A list of model identifiers (strings). If the endpoint is not
            available or fails, an empty list is returned.
        """
        try:
            result = self.api_client._make_request("GET", "/api/v1/devices/models")
            return result if isinstance(result, list) else []
        except ShureAPIError:
            logger.debug("Supported device models endpoint not available or failed")
            return []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return cast(
            dict[str, Any] | None,
            self.api_client._make_request("GET", f"/api/v1/devices/{device_id}"),
        )

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        result = self.api_client._make_request("GET", f"/api/v1/devices/{device_id}/channels")
        return result if isinstance(result, list) else []
