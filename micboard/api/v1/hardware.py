from typing import Any
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


class WirelessChassisViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for WirelessChassis."""

    serializer_class = WirelessChassisSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        user = self.request.user
        return WirelessChassis.objects.for_user(user=user)


class WirelessUnitViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for WirelessUnit."""

    serializer_class = WirelessUnitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        user = self.request.user
        return WirelessUnit.objects.for_user(user=user)


class RFChannelViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for RFChannel."""

    serializer_class = RFChannelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        user = self.request.user
        return RFChannel.objects.for_user(user=user)
