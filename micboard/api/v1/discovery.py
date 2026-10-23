from typing import TYPE_CHECKING

from django.db.models import QuerySet

from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.serializers.v1.discovery import DiscoveredDeviceSerializer

if TYPE_CHECKING:
    _DiscoveredDeviceViewSet = ReadOnlyModelViewSet[DiscoveredDevice]
else:
    _DiscoveredDeviceViewSet = ReadOnlyModelViewSet


class DiscoveredDeviceViewSet(_DiscoveredDeviceViewSet):
    """Read-only viewset for DiscoveredDevice."""

    serializer_class = DiscoveredDeviceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> QuerySet[DiscoveredDevice]:
        user = self.request.user
        if not user.is_authenticated:
            return DiscoveredDevice.objects.none()

        if user.is_superuser:
            return DiscoveredDevice.objects.all()

        return DiscoveredDevice.objects.none()
