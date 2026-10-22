from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.serializers.v1.discovery import redact_sensitive_keys

if TYPE_CHECKING:
    _MonitoringGroupSerializer = serializers.ModelSerializer[MonitoringGroup]
    _AlertSerializer = serializers.ModelSerializer[Alert]
else:
    _MonitoringGroupSerializer = serializers.ModelSerializer
    _AlertSerializer = serializers.ModelSerializer


class MonitoringGroupSerializer(_MonitoringGroupSerializer):
    class Meta:
        model = MonitoringGroup
        fields = "__all__"


class AlertSerializer(_AlertSerializer):
    class Meta:
        model = Alert
        fields = "__all__"

    def to_representation(self, instance: Alert) -> dict[str, Any]:
        ret = super().to_representation(instance)
        if ret.get("channel_data"):
            ret["channel_data"] = redact_sensitive_keys(ret["channel_data"])
        return ret
