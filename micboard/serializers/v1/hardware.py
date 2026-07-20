from rest_framework import serializers

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel


class WirelessChassisSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = WirelessChassis
        fields = "__all__"


class WirelessUnitSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = WirelessUnit
        fields = "__all__"


class RFChannelSerializer(serializers.ModelSerializer):  # type: ignore[misc]
    class Meta:
        model = RFChannel
        fields = "__all__"
