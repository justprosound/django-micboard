from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from micboard.models.settings.registry import Setting, SettingDefinition

if TYPE_CHECKING:
    _SettingDefinitionSerializer = serializers.ModelSerializer[SettingDefinition]
    _SettingSerializer = serializers.ModelSerializer[Setting]
else:
    _SettingDefinitionSerializer = serializers.ModelSerializer
    _SettingSerializer = serializers.ModelSerializer


class SettingDefinitionSerializer(_SettingDefinitionSerializer):
    class Meta:
        model = SettingDefinition
        fields = "__all__"

    def to_representation(self, instance: SettingDefinition) -> dict[str, Any]:
        """Serialize the setting definition and mask default values for sensitive keys."""
        ret = super().to_representation(instance)
        key = (ret.get("key") or "").lower()
        if any(
            substring in key for substring in ("secret", "password", "key", "token", "credential")
        ):
            ret["default_value"] = "********"
        return ret


class SettingSerializer(_SettingSerializer):
    class Meta:
        model = Setting
        fields = "__all__"

    def to_representation(self, instance: Setting) -> dict[str, Any]:
        """Serialize the setting override and mask stored values for sensitive definition keys."""
        ret = super().to_representation(instance)
        key = (instance.definition.key or "").lower()
        if any(
            substring in key for substring in ("secret", "password", "key", "token", "credential")
        ):
            ret["value"] = "********"
        return ret
