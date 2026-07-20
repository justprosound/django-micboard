from typing import Any

from rest_framework import serializers

from micboard.models.discovery.registry import DiscoveredDevice


def redact_sensitive_keys(data: Any) -> Any:
    """Recursively redact sensitive keys from dictionaries/lists."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            k_lower = k.lower()
            if any(
                substring in k_lower
                for substring in ("secret", "password", "key", "token", "credential", "community")
            ):
                redacted[k] = "********"
            else:
                redacted[k] = redact_sensitive_keys(v)
        return redacted
    if isinstance(data, list):
        return [redact_sensitive_keys(item) for item in data]
    return data


class DiscoveredDeviceSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = DiscoveredDevice
        fields = "__all__"

    def to_representation(self, instance: DiscoveredDevice) -> dict[str, Any]:
        ret = super().to_representation(instance)
        if ret.get("metadata"):
            ret["metadata"] = redact_sensitive_keys(ret["metadata"])
        return ret  # type: ignore[no-any-return]
