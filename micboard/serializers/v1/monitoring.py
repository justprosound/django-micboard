from typing import Any

from rest_framework import serializers

from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.serializers.v1.discovery import redact_sensitive_keys


class MonitoringGroupSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = MonitoringGroup
        fields = "__all__"


class AlertSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = Alert
        fields = "__all__"

    def to_representation(self, instance: Alert) -> dict[str, Any]:
        ret = super().to_representation(instance)
        if ret.get("channel_data"):
            ret["channel_data"] = redact_sensitive_keys(ret["channel_data"])
        return ret  # type: ignore[no-any-return]
