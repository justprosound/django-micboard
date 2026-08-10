from typing import Any

from rest_framework import serializers

from micboard.models.settings.registry import Setting, SettingDefinition


class SettingDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettingDefinition
        fields = "__all__"

    def to_representation(self, instance: SettingDefinition) -> dict[str, Any]:
        ret = super().to_representation(instance)
        key = (ret.get("key") or "").lower()
        if any(
            substring in key for substring in ("secret", "password", "key", "token", "credential")
        ):
            ret["default_value"] = "********"
        return ret


class SettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setting
        fields = "__all__"

    def to_representation(self, instance: Setting) -> dict[str, Any]:
        ret = super().to_representation(instance)
        key = (instance.definition.key or "").lower()
        if any(
            substring in key for substring in ("secret", "password", "key", "token", "credential")
        ):
            ret["value"] = "********"
        return ret
