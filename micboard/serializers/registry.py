"""Serializer registry and centralized serialization utilities for django-micboard.

Provides a single place to manage all serialization concerns:
- Model serializers
- Common serialization patterns
- Response format standards
- Serializer configuration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Type

if TYPE_CHECKING:
    from django.db.models import Model
    from rest_framework.serializers import Serializer

logger = logging.getLogger(__name__)


class SerializerRegistry:
    """Central registry for all model serializers.

    Provides:
    - Single lookup point for serializers by model
    - Consistent serialization patterns
    - Fallback handling for unknown models
    - Caching of serializer instances
    """

    def __init__(self):
        """Initialize the registry."""
        self._serializers: dict[str, dict[str, Any]] = {}
        self._populate_registry()

    def _populate_registry(self) -> None:
        """Populate with standard serializers."""
        from micboard.serializers.serializers import (
            ChannelSerializer,
            ChargerDetailSerializer,
            ChargerSummarySerializer,
            DiscoveredDeviceSerializer,
            GroupSerializer,
            ReceiverDetailSerializer,
            ReceiverSummarySerializer,
            TransmitterSerializer,
        )

        self.register(
            "WirelessChassis",
            summary=ReceiverSummarySerializer,
            detail=ReceiverDetailSerializer,
        )
        self.register(
            "WirelessUnit",
            default=TransmitterSerializer,
        )
        self.register(
            "RFChannel",
            default=ChannelSerializer,
        )
        self.register(
            "Charger",
            summary=ChargerSummarySerializer,
            detail=ChargerDetailSerializer,
        )
        self.register(
            "Group",
            default=GroupSerializer,
        )
        self.register(
            "DiscoveredDevice",
            default=DiscoveredDeviceSerializer,
        )

    def register(
        self,
        model_name: str,
        *,
        default: Type[Serializer] | None = None,
        summary: Type[Serializer] | None = None,
        detail: Type[Serializer] | None = None,
        list: Type[Serializer] | None = None,
    ) -> None:
        """Register serializers for a model.

        Args:
            model_name: Model class name (e.g., "Receiver")
            default: Default serializer for when no format specified
            summary: Lightweight serializer for lists/previews
            detail: Full serializer with all fields
            list: Serializer for list responses
        """
        self._serializers[model_name] = {
            "default": default or summary,
            "summary": summary,
            "detail": detail or default,
            "list": list or summary,
        }
        logger.debug(f"Registered serializers for {model_name}")

    def get_serializer(
        self,
        model_name: str,
        *,
        format: str = "default",
    ) -> Type[Serializer] | None:
        """Get serializer for a model and format.

        Args:
            model_name: Model class name (e.g., "WirelessChassis")
            format: Serializer format (default, summary, detail, list)
        """
        if model_name not in self._serializers:
            logger.warning(f"No serializer registered for {model_name}")
            return None

        serializers = self._serializers[model_name]

        # Fall back to default if specific format not available
        if format not in serializers:
            format = "default"

        return serializers.get(format)

    def serialize(
        self,
        obj: Model,
        *,
        format: str = "default",
        many: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Serialize a model instance or queryset.

        Args:
            obj: Model instance or queryset
            format: Serializer format (default, summary, detail, list)
            many: If True, serialize multiple objects

        Returns:
            Serialized data or None if serializer not found
        """
        model_name = obj.__class__.__name__ if not many else obj.model.__name__

        serializer_class = self.get_serializer(model_name, format=format)
        if not serializer_class:
            logger.warning(f"No serializer found for {model_name}")
            return None

        serializer = serializer_class(obj, many=many)
        return serializer.data

    def list_registered(self) -> list[str]:
        """List all registered model names."""
        return list(self._serializers.keys())


# Global registry instance
_registry: SerializerRegistry | None = None


def get_registry() -> SerializerRegistry:
    """Get the global serializer registry."""
    global _registry
    if _registry is None:
        _registry = SerializerRegistry()
    return _registry


def serialize_model(
    obj: Model,
    *,
    format: str = "default",
    many: bool = False,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Convenience function to serialize a model using registry.

    Args:
        obj: Model instance or queryset
        format: Serializer format
        many: If True, serialize multiple objects

    Returns:
        Serialized data
    """
    registry = get_registry()
    return registry.serialize(obj, format=format, many=many)


class StandardResponseBuilder:
    """Builds standardized response objects for API and real-time communications.

    Ensures consistent response format across all endpoints and WebSocket messages.
    """

    @staticmethod
    def build_device_list_response(
        devices: list[Model],
        *,
        format: str = "summary",
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        """Build a standardized device list response.

        Response format:
        {
            "devices": [...],
            "count": int,
            "format": "summary" | "detail",
            "timestamp": ISO string (if include_metadata)
        }

        Args:
            devices: List of device models
            format: Serialization format
            include_metadata: Include timestamp and metadata

        Returns:
            Standardized response dict
        """
        from django.utils import timezone

        from micboard.serializers import serialize_receivers

        serialized = serialize_receivers(devices, include_extra=(format == "detail"))

        response = {
            "devices": serialized,
            "count": len(devices),
            "format": format,
        }

        if include_metadata:
            response["timestamp"] = timezone.now().isoformat()

        return response

    @staticmethod
    def build_polling_result_response(
        result: dict[str, Any],
        include_devices: bool = True,
    ) -> dict[str, Any]:
        """Build a standardized polling result response.

        Response format:
        {
            "status": "success" | "partial" | "failed",
            "devices_created": int,
            "devices_updated": int,
            "errors": [...],
            "devices": [...] (if include_devices),
            "timestamp": ISO string
        }

        Args:
            result: Raw polling result
            include_devices: Include device list in response

        Returns:
            Standardized response dict
        """
        from django.utils import timezone

        created = result.get("devices_created", 0)
        updated = result.get("devices_updated", 0)
        errors = result.get("errors", [])

        status = "success"
        if errors:
            status = "partial" if (created + updated > 0) else "failed"

        response = {
            "status": status,
            "devices_created": created,
            "devices_updated": updated,
            "errors": errors,
            "timestamp": timezone.now().isoformat(),
        }

        return response

    @staticmethod
    def build_health_response(
        health_data: dict[str, Any],
        *,
        include_details: bool = True,
    ) -> dict[str, Any]:
        """Build a standardized health response.

        Response format:
        {
            "status": "healthy" | "degraded" | "unhealthy" | "error",
            "timestamp": ISO string,
            "details": {...} (if include_details)
        }

        Args:
            health_data: Raw health check result
            include_details: Include detail fields

        Returns:
            Standardized response dict
        """
        response = {
            "status": health_data.get("status", "unknown"),
            "timestamp": health_data.get("timestamp"),
        }

        if include_details and "details" in health_data:
            response["details"] = health_data["details"]

        return response

    @staticmethod
    def build_error_response(
        error_message: str,
        error_code: str | None = None,
        *,
        include_timestamp: bool = True,
    ) -> dict[str, Any]:
        """Build a standardized error response.

        Response format:
        {
            "error": error_message,
            "error_code": code (if provided),
            "timestamp": ISO string (if include_timestamp)
        }

        Args:
            error_message: Human-readable error message
            error_code: Optional error code/enum
            include_timestamp: Include timestamp

        Returns:
            Standardized error response dict
        """
        from django.utils import timezone

        response = {
            "error": error_message,
        }

        if error_code:
            response["error_code"] = error_code

        if include_timestamp:
            response["timestamp"] = timezone.now().isoformat()

        return response

    @staticmethod
    def build_websocket_update(
        update_type: str,
        data: Any,
        *,
        manufacturer: str | None = None,
    ) -> dict[str, Any]:
        """Build a standardized WebSocket update message.

        Message format:
        {
            "type": update_type,
            "data": data,
            "manufacturer": code (if provided),
            "timestamp": ISO string
        }

        Args:
            update_type: Type of update (device_update, health, etc)
            data: Update data
            manufacturer: Optional manufacturer code

        Returns:
            Standardized WebSocket message dict
        """
        from django.utils import timezone

        message = {
            "type": update_type,
            "data": data,
            "timestamp": timezone.now().isoformat(),
        }

        if manufacturer:
            message["manufacturer"] = manufacturer

        return message
