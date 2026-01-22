"""
Django REST Framework viewsets for all core models.

Provides full CRUD API endpoints with filtering, searching, and bulk operations.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q, QuerySet
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from micboard.decorators import rate_limit_view
from micboard.models import (
    Channel,
    Group,
    Location,
    Manufacturer,
    Receiver,
    Room,
    Transmitter,
)
from micboard.models.configuration import (
    ConfigurationAuditLog,
    ManufacturerConfiguration,
)
from micboard.serializers.drf import (
    BulkDeviceActionSerializer,
    ChannelDetailSerializer,
    ChannelSerializer,
    ConfigurationAuditLogSerializer,
    GroupSerializer,
    HealthStatusSerializer,
    LocationSerializer,
    ManufacturerConfigurationSerializer,
    ManufacturerDetailSerializer,
    ManufacturerSerializer,
    ReceiverDetailSerializer,
    ReceiverListSerializer,
    ReceiverSerializer,
    RoomSerializer,
    TransmitterDetailSerializer,
    TransmitterListSerializer,
    TransmitterSerializer,
)
from micboard.services.manufacturer_service import get_all_services, get_service

logger = logging.getLogger(__name__)


class BaseViewSet(viewsets.ModelViewSet):
    """Base viewset with common functionality."""

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    @action(detail=False, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def stats(self, request: Request) -> Response:
        """Get statistics for this model."""
        queryset = self.get_queryset()
        return Response(
            {
                "total_count": queryset.count(),
                "online_count": queryset.filter(is_online=True).count()
                if "is_online" in queryset.model._meta.fields
                else None,
            }
        )


class ManufacturerViewSet(BaseViewSet):
    """ViewSet for Manufacturer model."""

    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        """Use detailed serializer for retrieve."""
        if self.action == "retrieve":
            return ManufacturerDetailSerializer
        return ManufacturerSerializer

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def receivers(self, request: Request, pk: int | None = None) -> Response:
        """Get all receivers for this manufacturer."""
        manufacturer = self.get_object()
        receivers = manufacturer.receiver_set.all()
        serializer = ReceiverListSerializer(receivers, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def transmitters(self, request: Request, pk: int | None = None) -> Response:
        """Get all transmitters for this manufacturer."""
        manufacturer = self.get_object()
        transmitters = manufacturer.transmitter_set.all()
        serializer = TransmitterListSerializer(transmitters, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def status(self, request: Request, pk: int | None = None) -> Response:
        """Get status for this manufacturer."""
        manufacturer = self.get_object()
        receivers = manufacturer.receiver_set.all()
        transmitters = manufacturer.transmitter_set.all()

        return Response(
            {
                "code": manufacturer.code,
                "name": manufacturer.name,
                "receivers": {
                    "total": receivers.count(),
                    "online": receivers.filter(is_online=True).count(),
                    "offline": receivers.filter(is_online=False).count(),
                },
                "transmitters": {
                    "total": transmitters.count(),
                    "online": transmitters.filter(is_online=True).count(),
                    "offline": transmitters.filter(is_online=False).count(),
                },
            }
        )


class ManufacturerConfigurationViewSet(BaseViewSet):
    """ViewSet for ManufacturerConfiguration model."""

    queryset = ManufacturerConfiguration.objects.all()
    serializer_class = ManufacturerConfigurationSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["name", "is_active", "last_validated"]
    ordering = ["name"]

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=20, window_seconds=60)
    def validate(self, request: Request, pk: int | None = None) -> Response:
        """Validate the configuration."""
        config = self.get_object()
        result = config.validate()
        config.save()

        return Response(
            {
                "is_valid": result["is_valid"],
                "errors": result["errors"],
                "last_validated": config.last_validated.isoformat()
                if config.last_validated
                else None,
            }
        )

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=20, window_seconds=60)
    def apply(self, request: Request, pk: int | None = None) -> Response:
        """Apply the configuration to the service."""
        config = self.get_object()

        # Validate first
        if not config.is_valid:
            result = config.validate()
            config.save()
            if not config.is_valid:
                return Response(
                    {
                        "success": False,
                        "message": "Configuration is not valid",
                        "errors": result["errors"],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Apply to service
        success = config.apply_to_service()
        return Response(
            {
                "success": success,
                "message": "Configuration applied to service"
                if success
                else "Failed to apply configuration",
            }
        )

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def audit_logs(self, request: Request, pk: int | None = None) -> Response:
        """Get audit logs for this configuration."""
        config = self.get_object()
        logs = config.audit_logs.all()
        serializer = ConfigurationAuditLogSerializer(logs, many=True)
        return Response(serializer.data)


class LocationViewSet(BaseViewSet):
    """ViewSet for Location model."""

    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    search_fields = ["name", "building", "description"]
    ordering_fields = ["name", "building", "created_at"]
    ordering = ["name"]


class RoomViewSet(BaseViewSet):
    """ViewSet for Room model."""

    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    search_fields = ["name", "description"]
    ordering_fields = ["name", "location", "created_at"]
    ordering = ["location", "name"]

    def get_queryset(self) -> QuerySet:
        """Filter by location if provided."""
        queryset = super().get_queryset()
        location_id = self.request.query_params.get("location_id")
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        return queryset


class GroupViewSet(BaseViewSet):
    """ViewSet for Group model."""

    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def add_members(self, request: Request, pk: int | None = None) -> Response:
        """Add devices to group."""
        group = self.get_object()
        device_ids = request.data.get("device_ids", [])

        if not device_ids:
            return Response(
                {"message": "device_ids required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Add receivers
        receivers = Receiver.objects.filter(id__in=device_ids)
        group.members.add(*receivers)

        # Add transmitters
        transmitters = Transmitter.objects.filter(id__in=device_ids)
        group.members.add(*transmitters)

        return Response(
            {
                "message": f"Added {receivers.count() + transmitters.count()} devices to group"
            }
        )

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def remove_members(self, request: Request, pk: int | None = None) -> Response:
        """Remove devices from group."""
        group = self.get_object()
        device_ids = request.data.get("device_ids", [])

        if not device_ids:
            return Response(
                {"message": "device_ids required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove receivers and transmitters
        receivers = Receiver.objects.filter(id__in=device_ids)
        transmitters = Transmitter.objects.filter(id__in=device_ids)
        group.members.remove(*receivers, *transmitters)

        return Response(
            {
                "message": f"Removed {receivers.count() + transmitters.count()} devices from group"
            }
        )


class ChannelViewSet(BaseViewSet):
    """ViewSet for Channel model."""

    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    search_fields = ["name", "receiver__name"]
    ordering_fields = ["number", "frequency", "created_at"]
    ordering = ["receiver", "number"]

    def get_serializer_class(self):
        """Use detailed serializer for retrieve."""
        if self.action == "retrieve":
            return ChannelDetailSerializer
        return ChannelSerializer

    def get_queryset(self) -> QuerySet:
        """Filter by receiver if provided."""
        queryset = super().get_queryset()
        receiver_id = self.request.query_params.get("receiver_id")
        if receiver_id:
            queryset = queryset.filter(receiver_id=receiver_id)

        active_only = self.request.query_params.get("active_only")
        if active_only:
            queryset = queryset.filter(is_active=True)

        return queryset


class ReceiverViewSet(BaseViewSet):
    """ViewSet for Receiver model."""

    queryset = Receiver.objects.all()
    serializer_class = ReceiverSerializer
    search_fields = ["name", "model", "ip_address", "hostname"]
    ordering_fields = ["name", "is_online", "created_at"]
    ordering = ["-is_online", "name"]

    def get_serializer_class(self):
        """Use appropriate serializer based on action."""
        if self.action == "retrieve":
            return ReceiverDetailSerializer
        elif self.action == "list":
            return ReceiverListSerializer
        return ReceiverSerializer

    def get_queryset(self) -> QuerySet:
        """Filter by manufacturer and online status if provided."""
        queryset = super().get_queryset()

        manufacturer_id = self.request.query_params.get("manufacturer_id")
        if manufacturer_id:
            queryset = queryset.filter(manufacturer_id=manufacturer_id)

        online_only = self.request.query_params.get("online_only")
        if online_only:
            queryset = queryset.filter(is_online=True)

        return queryset

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def channels(self, request: Request, pk: int | None = None) -> Response:
        """Get all channels for this receiver."""
        receiver = self.get_object()
        channels = receiver.channel_set.all()
        serializer = ChannelDetailSerializer(channels, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def signal_quality(self, request: Request, pk: int | None = None) -> Response:
        """Get signal quality metrics."""
        receiver = self.get_object()
        channels = receiver.channel_set.exclude(rf_level__isnull=True)

        if not channels.exists():
            return Response(
                {
                    "message": "No signal data available",
                    "avg_rf": None,
                    "max_rf": None,
                    "min_rf": None,
                }
            )

        rf_levels = [c.rf_level for c in channels]
        return Response(
            {
                "avg_rf": sum(rf_levels) / len(rf_levels),
                "max_rf": max(rf_levels),
                "min_rf": min(rf_levels),
                "sample_count": len(rf_levels),
            }
        )

    @action(detail=False, methods=["post"])
    @rate_limit_view(max_requests=20, window_seconds=60)
    def bulk_action(self, request: Request) -> Response:
        """Perform bulk actions on multiple receivers."""
        serializer = BulkDeviceActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_ids = serializer.validated_data["device_ids"]
        action_name = serializer.validated_data["action"]
        receivers = Receiver.objects.filter(id__in=device_ids)

        if action_name == "activate":
            receivers.update(is_active=True)
            message = f"Activated {receivers.count()} receivers"
        elif action_name == "deactivate":
            receivers.update(is_active=False)
            message = f"Deactivated {receivers.count()} receivers"
        else:
            return Response(
                {"message": f"Unknown action: {action_name}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            message,
            extra={"action": action_name, "count": receivers.count()},
        )
        return Response({"message": message, "count": receivers.count()})


class TransmitterViewSet(BaseViewSet):
    """ViewSet for Transmitter model."""

    queryset = Transmitter.objects.all()
    serializer_class = TransmitterSerializer
    search_fields = ["name", "model", "ip_address", "hostname"]
    ordering_fields = ["name", "is_online", "created_at"]
    ordering = ["-is_online", "name"]

    def get_serializer_class(self):
        """Use appropriate serializer based on action."""
        if self.action == "retrieve":
            return TransmitterDetailSerializer
        elif self.action == "list":
            return TransmitterListSerializer
        return TransmitterSerializer

    def get_queryset(self) -> QuerySet:
        """Filter by manufacturer and online status if provided."""
        queryset = super().get_queryset()

        manufacturer_id = self.request.query_params.get("manufacturer_id")
        if manufacturer_id:
            queryset = queryset.filter(manufacturer_id=manufacturer_id)

        online_only = self.request.query_params.get("online_only")
        if online_only:
            queryset = queryset.filter(is_online=True)

        return queryset

    @action(detail=False, methods=["post"])
    @rate_limit_view(max_requests=20, window_seconds=60)
    def bulk_action(self, request: Request) -> Response:
        """Perform bulk actions on multiple transmitters."""
        serializer = BulkDeviceActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_ids = serializer.validated_data["device_ids"]
        action_name = serializer.validated_data["action"]
        transmitters = Transmitter.objects.filter(id__in=device_ids)

        if action_name == "activate":
            transmitters.update(is_active=True)
            message = f"Activated {transmitters.count()} transmitters"
        elif action_name == "deactivate":
            transmitters.update(is_active=False)
            message = f"Deactivated {transmitters.count()} transmitters"
        else:
            return Response(
                {"message": f"Unknown action: {action_name}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            message,
            extra={"action": action_name, "count": transmitters.count()},
        )
        return Response({"message": message, "count": transmitters.count()})


class ServiceHealthViewSet(viewsets.ViewSet):
    """ViewSet for service health status (read-only)."""

    permission_classes = [permissions.IsAuthenticated]

    @rate_limit_view(max_requests=60, window_seconds=60)
    def list(self, request: Request) -> Response:
        """Get health status for all services."""
        services = get_all_services()
        health_data = []

        for service in services:
            health = service.check_health()
            receivers = service.get_devices() if hasattr(service, "get_devices") else []
            online_count = sum(1 for r in receivers if r.get("is_online", False))

            health_data.append(
                {
                    "code": service.code,
                    "name": service.name,
                    "status": health.get("status"),
                    "message": health.get("message"),
                    "device_count": len(receivers),
                    "online_count": online_count,
                    "last_poll": service.last_poll.isoformat()
                    if service.last_poll
                    else None,
                    "error_count": service.error_count,
                }
            )

        return Response(health_data)

    @rate_limit_view(max_requests=60, window_seconds=60)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Get health status for a specific service by code."""
        service_code = pk  # pk is used for service code in this viewset
        service = get_service(service_code)
        if not service:
            return Response(
                {"message": f"Service not found: {service_code}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        health = service.check_health()
        receivers = service.get_devices() if hasattr(service, "get_devices") else []
        online_count = sum(1 for r in receivers if r.get("is_online", False))

        return Response(
            {
                "code": service.code,
                "name": service.name,
                "status": health.get("status"),
                "message": health.get("message"),
                "device_count": len(receivers),
                "online_count": online_count,
                "last_poll": service.last_poll.isoformat()
                if service.last_poll
                else None,
                "error_count": service.error_count,
            }
        )
