from typing import TYPE_CHECKING, Any

from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.serializers.v1.hardware import (
    RFChannelSerializer,
    WirelessChassisSerializer,
    WirelessUnitSerializer,
)
from micboard.services.shared.visibility import visible_to

if TYPE_CHECKING:
    _WirelessChassisViewSet = ReadOnlyModelViewSet[WirelessChassis]
    _WirelessUnitViewSet = ReadOnlyModelViewSet[WirelessUnit]
    _RFChannelViewSet = ReadOnlyModelViewSet[RFChannel]
else:
    _WirelessChassisViewSet = ReadOnlyModelViewSet
    _WirelessUnitViewSet = ReadOnlyModelViewSet
    _RFChannelViewSet = ReadOnlyModelViewSet


class WirelessChassisViewSet(_WirelessChassisViewSet):
    """Read-only viewset for WirelessChassis."""

    serializer_class = WirelessChassisSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        """Return wireless chassis visible to the authenticated user."""
        user = self.request.user
        if not user.is_authenticated:
            return WirelessChassis.objects.none()
        return visible_to(WirelessChassis, user=user)


class WirelessUnitViewSet(_WirelessUnitViewSet):
    """Read-only viewset for WirelessUnit."""

    serializer_class = WirelessUnitSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        """Return wireless units visible to the authenticated user."""
        user = self.request.user
        if not user.is_authenticated:
            return WirelessUnit.objects.none()
        return visible_to(WirelessUnit, user=user)


class RFChannelViewSet(_RFChannelViewSet):
    """Read-only viewset for RFChannel."""

    serializer_class = RFChannelSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        """Return RF channels visible to the authenticated user."""
        user = self.request.user
        if not user.is_authenticated:
            return RFChannel.objects.none()
        return visible_to(RFChannel, user=user)
