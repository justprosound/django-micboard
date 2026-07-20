from typing import Any

from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.serializers.v1.discovery import DiscoveredDeviceSerializer


class DiscoveredDeviceViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for DiscoveredDevice."""

    serializer_class = DiscoveredDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        user = self.request.user
        if not user.is_authenticated:
            return DiscoveredDevice.objects.none()

        if user.is_superuser:
            return DiscoveredDevice.objects.all()

        return DiscoveredDevice.objects.none()
