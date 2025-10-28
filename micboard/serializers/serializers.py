from typing import ClassVar

from rest_framework import serializers

from micboard.models import (
    Channel,
    Charger,
    ChargerSlot,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Receiver,
    Transmitter,
)


class TransmitterSerializer(serializers.ModelSerializer):
    battery_health = serializers.CharField(read_only=True)
    signal_quality = serializers.CharField(source="get_signal_quality", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Transmitter
        fields: ClassVar[list[str]] = [
            "slot",
            "battery",
            "battery_charge",
            "battery_percentage",
            "audio_level",
            "rf_level",
            "frequency",
            "antenna",
            "tx_offset",
            "quality",
            "runtime",
            "status",
            "name",
            "name_raw",
            "updated_at",
            "battery_health",
            "signal_quality",
            "is_active",
        ]


class ChannelSerializer(serializers.ModelSerializer):
    transmitter = TransmitterSerializer(read_only=True)
    has_transmitter = serializers.BooleanField(read_only=True)

    class Meta:
        model = Channel
        fields: ClassVar[list[str]] = [
            "channel_number",
            "has_transmitter",
            "transmitter",
        ]

    def to_representation(self, instance):
        """Customize representation: omit transmitter key when it's None.

        Tests expect that channels without a transmitter do not include a
        'transmitter' key in the serialized dict (rather than having it set
        to null/None).
        """
        ret = super().to_representation(instance)
        if ret.get("transmitter") is None:
            ret.pop("transmitter", None)
        return ret


class ReceiverSummarySerializer(serializers.ModelSerializer):
    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.CharField(read_only=True)
    channel_count = serializers.IntegerField(source="get_channel_count", read_only=True)

    class Meta:
        model = Receiver
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "name",
            "device_type",
            "manufacturer_code",
            "ip",
            "is_active",
            "health_status",
            "last_seen",
            "channel_count",
        ]


class ReceiverDetailSerializer(serializers.ModelSerializer):
    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.CharField(read_only=True)
    is_healthy = serializers.BooleanField(read_only=True)
    channel_count = serializers.IntegerField(source="get_channel_count", read_only=True)
    channels = ChannelSerializer(many=True, read_only=True)

    class Meta:
        model = Receiver
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "ip",
            "manufacturer_code",
            "device_type",
            "name",
            "firmware_version",
            "is_active",
            "last_seen",
            "health_status",
            "is_healthy",
            "channel_count",
            "channels",
        ]


class ChargerSlotSerializer(serializers.ModelSerializer):
    transmitter_name = serializers.SerializerMethodField()
    battery_level = serializers.SerializerMethodField()
    charging = serializers.BooleanField(source="charging_status", read_only=True)

    class Meta:
        model = ChargerSlot
        fields: ClassVar[list[str]] = [
            "slot_number",
            "is_occupied",
            "transmitter_name",
            "battery_level",
            "charging",
        ]

    def get_transmitter_name(self, obj):
        if obj.transmitter:
            return obj.transmitter.name
        return None

    def get_battery_level(self, obj):
        if obj.transmitter:
            return obj.transmitter.battery_percentage
        return None


class ChargerSummarySerializer(serializers.ModelSerializer):
    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.CharField(read_only=True)
    slot_count = serializers.IntegerField(source="get_slot_count", read_only=True)

    class Meta:
        model = Charger
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "name",
            "device_type",
            "manufacturer_code",
            "ip",
            "is_active",
            "health_status",
            "last_seen",
            "slot_count",
        ]


class ChargerDetailSerializer(serializers.ModelSerializer):
    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.CharField(read_only=True)
    is_healthy = serializers.BooleanField(read_only=True)
    slot_count = serializers.IntegerField(source="get_slot_count", read_only=True)
    slots = ChargerSlotSerializer(many=True, read_only=True)

    class Meta:
        model = Charger
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "ip",
            "manufacturer_code",
            "device_type",
            "name",
            "firmware_version",
            "is_active",
            "last_seen",
            "health_status",
            "is_healthy",
            "slot_count",
            "slots",
        ]


class DiscoveredDeviceSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="device_type", read_only=True)

    class Meta:
        model = DiscoveredDevice
        fields: ClassVar[list[str]] = [
            "ip",
            "type",
            "channels",
            "discovered_at",
        ]


class GroupSerializer(serializers.ModelSerializer):
    group = serializers.SerializerMethodField()

    def get_group(self, obj: Group) -> int:
        return int(obj.group_number)

    class Meta:
        model = Group
        fields: ClassVar[list[str]] = [
            "group",
            "group_number",
            "title",
            "slots",
            "hide_charts",
        ]


class DeviceAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceAssignment
        fields = "__all__"
