from typing import Any

from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.monitoring.group import MonitoringGroup
from micboard.serializers.v1.monitoring import AlertSerializer, MonitoringGroupSerializer
from micboard.services.monitoring.alerts import get_alerts_for_user
from micboard.services.shared.visibility import visible_to


class MonitoringGroupViewSet(ReadOnlyModelViewSet):
    """Read-only viewset for MonitoringGroup."""

    serializer_class = MonitoringGroupSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        return visible_to(MonitoringGroup, user=self.request.user)


class AlertViewSet(ReadOnlyModelViewSet):
    """Read-only viewset for Alert."""

    serializer_class = AlertSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> Any:
        user = self.request.user
        return get_alerts_for_user(user)
