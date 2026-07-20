from typing import Any

from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.monitoring.group import MonitoringGroup
from micboard.serializers.v1.monitoring import AlertSerializer, MonitoringGroupSerializer
from micboard.services.monitoring.alerts import get_alerts_for_user


class MonitoringGroupViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for MonitoringGroup."""

    serializer_class = MonitoringGroupSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        user = self.request.user
        if not user.is_authenticated:
            return MonitoringGroup.objects.none()

        if user.is_superuser:
            return MonitoringGroup.objects.all()

        return user.monitoring_groups.filter(is_active=True)


class AlertViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for Alert."""

    serializer_class = AlertSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        user = self.request.user
        return get_alerts_for_user(user)
