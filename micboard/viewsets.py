"""DRF ViewSets using service layer.

Production-ready viewsets that delegate business logic to services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from micboard.decorators import rate_limit_view
from micboard.models import RFChannel
from micboard.serializers import (
    serialize_assignment,
    serialize_assignments,
    serialize_connection,
    serialize_connections,
    serialize_location,
    serialize_locations,
    serialize_receiver,
    serialize_receivers,
    serialize_transmitter,
    serialize_transmitters,
)
from micboard.services import (
    AssignmentService,
    ConnectionHealthService,
    DeviceService,
    LocationService,
)
from micboard.services.exceptions import (
    AssignmentAlreadyExistsError,
    DeviceNotFoundError,
    LocationAlreadyExistsError,
)

if TYPE_CHECKING:
    from rest_framework.request import Request


class ReceiverViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for WirelessChassis model using DeviceService."""

    @rate_limit_view(max_requests=120, window_seconds=60)
    def list(self, request: Request) -> Response:
        """List all active receivers."""
        receivers = DeviceService.get_active_receivers()
        data = serialize_receivers(receivers)
        return Response(data)

    @rate_limit_view(max_requests=120, window_seconds=60)
    def retrieve(self, request: Request, pk: int = None) -> Response:
        """Retrieve single receiver by ID."""
        try:
            receiver = DeviceService.get_receiver_by_id(receiver_id=pk)
            data = serialize_receiver(receiver)
            return Response(data)
        except DeviceNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def online(self, request: Request) -> Response:
        """List only online receivers."""
        receivers = DeviceService.get_online_receivers()
        data = serialize_receivers(receivers)
        return Response(data)

    @action(detail=False, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def low_battery(self, request: Request) -> Response:
        """List receivers with low battery."""
        threshold = int(request.query_params.get("threshold", 20))
        receivers = DeviceService.get_low_battery_receivers(threshold=threshold)
        data = serialize_receivers(receivers)
        return Response(data)

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=30, window_seconds=60)
    def sync_status(self, request: Request, pk: int = None) -> Response:
        """Sync device status."""
        try:
            receiver = DeviceService.get_receiver_by_id(receiver_id=pk)
            online = request.data.get("online", True)

            DeviceService.sync_device_status(device_obj=receiver, online=online)

            data = serialize_receiver(receiver)
            return Response(data)
        except DeviceNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class TransmitterViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for WirelessUnit model using DeviceService."""

    @rate_limit_view(max_requests=120, window_seconds=60)
    def list(self, request: Request) -> Response:
        """List all active transmitters."""
        transmitters = DeviceService.get_active_transmitters()
        data = serialize_transmitters(transmitters)
        return Response(data)

    @rate_limit_view(max_requests=120, window_seconds=60)
    def retrieve(self, request: Request, pk: int = None) -> Response:
        """Retrieve single transmitter by ID."""
        try:
            transmitter = DeviceService.get_transmitter_by_id(transmitter_id=pk)
            data = serialize_transmitter(transmitter)
            return Response(data)
        except DeviceNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def low_battery(self, request: Request) -> Response:
        """List transmitters with low battery."""
        threshold = int(request.query_params.get("threshold", 20))
        transmitters = DeviceService.get_low_battery_transmitters(threshold=threshold)
        data = serialize_transmitters(transmitters)
        return Response(data)


class AssignmentViewSet(viewsets.ViewSet):
    """ViewSet for DeviceAssignment model using AssignmentService."""

    @rate_limit_view(max_requests=120, window_seconds=60)
    def list(self, request: Request) -> Response:
        """List all assignments."""
        user_id = request.query_params.get("user_id")
        channel_id = request.query_params.get("channel_id")

        if user_id:
            assignments = AssignmentService.get_assignments_for_user(user=int(user_id))
        elif channel_id:
            assignments = AssignmentService.get_assignments_for_device(device_id=int(channel_id))
        else:
            from micboard.models import DeviceAssignment

            assignments = DeviceAssignment.objects.all()

        data = serialize_assignments(assignments)
        return Response(data)

    @rate_limit_view(max_requests=30, window_seconds=60)
    def create(self, request: Request) -> Response:
        """Create new assignment."""
        user_id = request.data.get("user_id")
        channel_id = request.data.get("channel_id")
        alert_enabled = request.data.get("alert_enabled", False)

        if not user_id or not channel_id:
            return Response(
                {"error": "user_id and channel_id are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(id=user_id)

            channel = RFChannel.objects.get(id=channel_id)

            assignment = AssignmentService.create_assignment(
                user=user, channel=channel, alert_enabled=alert_enabled
            )

            data = serialize_assignment(assignment)
            return Response(data, status=status.HTTP_201_CREATED)

        except AssignmentAlreadyExistsError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        except DeviceNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except RFChannel.DoesNotExist:
            return Response({"error": "Channel not found"}, status=status.HTTP_404_NOT_FOUND)

    @rate_limit_view(max_requests=30, window_seconds=60)
    def destroy(self, request: Request, pk: int = None) -> Response:
        """Delete assignment."""
        try:
            from micboard.models import Assignment

            assignment = Assignment.objects.get(id=pk)

            AssignmentService.delete_assignment(assignment=assignment)

            return Response(status=status.HTTP_204_NO_CONTENT)

        except Assignment.DoesNotExist:
            return Response({"error": "Assignment not found"}, status=status.HTTP_404_NOT_FOUND)


class LocationViewSet(viewsets.ViewSet):
    """ViewSet for Location model using LocationService."""

    @rate_limit_view(max_requests=120, window_seconds=60)
    def list(self, request: Request) -> Response:
        """List all locations."""
        locations = LocationService.list_all_locations()
        data = serialize_locations(locations)
        return Response(data)

    @rate_limit_view(max_requests=30, window_seconds=60)
    def create(self, request: Request) -> Response:
        """Create new location."""
        name = request.data.get("name")
        description = request.data.get("description", "")

        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            location = LocationService.create_location(name=name, description=description)

            data = serialize_location(location)
            return Response(data, status=status.HTTP_201_CREATED)

        except LocationAlreadyExistsError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=30, window_seconds=60)
    def assign_device(self, request: Request, pk: int = None) -> Response:
        """Assign device to location."""
        device_id = request.data.get("device_id")

        if not device_id:
            return Response({"error": "device_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from micboard.models import Location

            location = Location.objects.get(id=pk)
            device = DeviceService.get_receiver_by_id(receiver_id=device_id)

            LocationService.assign_device_to_location(device_obj=device, location_obj=location)

            data = serialize_location(location)
            return Response(data)

        except Location.DoesNotExist:
            return Response({"error": "Location not found"}, status=status.HTTP_404_NOT_FOUND)
        except DeviceNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class ConnectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for RealTimeConnection model using ConnectionHealthService."""

    @rate_limit_view(max_requests=120, window_seconds=60)
    def list(self, request: Request) -> Response:
        """List all connections."""
        manufacturer_code = request.query_params.get("manufacturer_code")

        if manufacturer_code:
            connections = ConnectionHealthService.get_connections_for_manufacturer(
                manufacturer_code=manufacturer_code
            )
        else:
            from micboard.models import RealTimeConnection

            connections = RealTimeConnection.objects.all()

        data = serialize_connections(connections)
        return Response(data)

    @action(detail=False, methods=["get"])
    @rate_limit_view(max_requests=60, window_seconds=60)
    def unhealthy(self, request: Request) -> Response:
        """List unhealthy connections."""
        timeout = int(request.query_params.get("timeout", 60))

        unhealthy = ConnectionHealthService.get_unhealthy_connections(
            heartbeat_timeout_seconds=timeout
        )

        return Response(unhealthy)

    @action(detail=True, methods=["post"])
    @rate_limit_view(max_requests=30, window_seconds=60)
    def heartbeat(self, request: Request, pk: int = None) -> Response:
        """Update connection heartbeat."""
        try:
            from micboard.models import RealTimeConnection

            connection = RealTimeConnection.objects.get(id=pk)

            ConnectionHealthService.update_heartbeat(connection_obj=connection)

            data = serialize_connection(connection)
            return Response(data)

        except RealTimeConnection.DoesNotExist:
            return Response({"error": "Connection not found"}, status=status.HTTP_404_NOT_FOUND)
