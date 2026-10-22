from typing import TYPE_CHECKING

from rest_framework import serializers

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel

if TYPE_CHECKING:
    _WirelessChassisSerializer = serializers.ModelSerializer[WirelessChassis]
    _WirelessUnitSerializer = serializers.ModelSerializer[WirelessUnit]
    _RFChannelSerializer = serializers.ModelSerializer[RFChannel]
else:
    _WirelessChassisSerializer = serializers.ModelSerializer
    _WirelessUnitSerializer = serializers.ModelSerializer
    _RFChannelSerializer = serializers.ModelSerializer


class WirelessChassisSerializer(_WirelessChassisSerializer):
    class Meta:
        model = WirelessChassis
        fields = "__all__"


class WirelessUnitSerializer(_WirelessUnitSerializer):
    class Meta:
        model = WirelessUnit
        fields = "__all__"


class RFChannelSerializer(_RFChannelSerializer):
    class Meta:
        model = RFChannel
        fields = "__all__"
