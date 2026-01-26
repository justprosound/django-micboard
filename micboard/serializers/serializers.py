"""Core DRF serializers used across Micboard APIs and helpers."""

# file: micboard/serializers/serializers.py
from typing import ClassVar

from rest_framework import serializers

from micboard.models import (
    Charger,
    ChargerSlot,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    RFChannel,
    WirelessChassis,
    WirelessUnit,
)


class TransmitterSerializer(serializers.ModelSerializer):
    """Serialize wireless transmitters and their telemetry."""

    battery_health = serializers.SerializerMethodField(read_only=True)
    battery_info = serializers.SerializerMethodField(read_only=True)
    signal_quality = serializers.CharField(source="get_signal_quality", read_only=True)
    is_active = serializers.SerializerMethodField(read_only=True)

    class Meta:
        """Serializer configuration for transmitters."""

        model = WirelessUnit
        fields: ClassVar[list[str]] = [
            # Identity
            "slot",
            "serial_number",
            "model",
            # Real-time metrics
            "battery",
            "battery_charge",
            "battery_percentage",
            "battery_type",
            "battery_runtime",
            "audio_level",
            "rf_level",
            "frequency",
            "antenna",
            "tx_offset",
            "quality",
            # Status
            "status",
            "name",
            "firmware_version",
            "updated_at",
            # Computed fields
            "battery_health",
            "battery_info",
            "signal_quality",
            "is_active",
        ]

    def get_battery_health(self, obj: WirelessUnit) -> str:
        """Compute battery health status for serialization."""
        return obj.get_battery_health()

    def get_battery_info(self, obj: WirelessUnit) -> dict:
        """Return comprehensive battery status dict."""
        return {
            "level": obj.battery,
            "percentage": obj.battery_percentage,
            "charge": obj.battery_charge,
            "runtime": obj.battery_runtime,
            "type": obj.battery_type,
            "health": obj.get_battery_health(),
            "charging": obj.charging_status,
        }

    def get_is_active(self, obj: WirelessUnit) -> bool:
        """Check if wireless unit is active for serialization."""
        return not obj.is_idle


class ChannelSerializer(serializers.ModelSerializer):
    """Serialize RF channels and active transmitter info."""

    transmitter = TransmitterSerializer(read_only=True, source="active_wireless_unit")
    has_transmitter = serializers.BooleanField(read_only=True, source="active_wireless_unit")

    class Meta:
        """Serializer configuration for RF channels."""

        model = RFChannel
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
    """Serialize receiver summary metrics without channels."""

    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.SerializerMethodField(read_only=True)
    channel_count = serializers.IntegerField(source="rf_channels.count", read_only=True)
    device_name = serializers.CharField(source="name", read_only=True)
    device_type = serializers.CharField(source="role", read_only=True)
    ip_address = serializers.IPAddressField(source="ip", read_only=True)

    class Meta:
        """Serializer configuration for receiver summary payloads."""

        model = WirelessChassis
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "device_name",
            "device_type",
            "manufacturer_code",
            "ip_address",
            "is_active",
            "health_status",
            "last_seen",
            "channel_count",
        ]

    def get_health_status(self, obj: WirelessChassis) -> str:
        """Compute health status for serialization."""
        return obj.get_health_status()

    def get_is_active(self, obj: WirelessChassis) -> bool:
        """Check if chassis is active for serialization."""
        return obj.is_active


class ReceiverDetailSerializer(serializers.ModelSerializer):
    """Serialize receiver details including channels."""

    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.SerializerMethodField(read_only=True)
    is_healthy = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.SerializerMethodField(read_only=True)
    channel_count = serializers.IntegerField(source="rf_channels.count", read_only=True)
    channels = ChannelSerializer(many=True, read_only=True, source="rf_channels")
    device_name = serializers.CharField(source="name", read_only=True)
    device_type = serializers.CharField(source="role", read_only=True)
    ip_address = serializers.IPAddressField(source="ip", read_only=True)

    class Meta:
        """Serializer configuration for receiver detail payloads."""

        model = WirelessChassis
        fields: ClassVar[list[str]] = [
            "api_device_id",
            "ip_address",
            "manufacturer_code",
            "device_type",
            "device_name",
            "firmware_version",
            "is_active",
            "last_seen",
            "health_status",
            "is_healthy",
            "channel_count",
            "channels",
        ]

    def get_health_status(self, obj: WirelessChassis) -> str:
        """Compute health status for serialization."""
        return obj.get_health_status()

    def get_is_healthy(self, obj: WirelessChassis) -> bool:
        """Check if receiver is healthy for serialization."""
        return obj.get_health_status() == "healthy"

    def get_is_active(self, obj: WirelessChassis) -> bool:
        """Check if receiver is active for serialization."""
        return obj.is_active_at_time()


class ChargerSlotSerializer(serializers.ModelSerializer):
    """Serialize slot status within a charger."""

    transmitter_name = serializers.SerializerMethodField()
    battery_level = serializers.IntegerField(source="battery_percent", read_only=True)

    class Meta:
        """Serializer configuration for charger slots."""

        model = ChargerSlot
        fields: ClassVar[list[str]] = [
            "slot_number",
            "is_occupied",
            "transmitter_name",
            "battery_level",
            "device_firmware_version",
            "device_status",
        ]

    def get_transmitter_name(self, obj):
        """Return a human-readable transmitter label for the slot."""
        if obj.device_model and obj.device_serial:
            return f"{obj.device_model} ({obj.device_serial})"
        elif obj.device_serial:
            return obj.device_serial
        return None


class ChargerSummarySerializer(serializers.ModelSerializer):
    """Serialize high-level charger information."""

    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.SerializerMethodField(read_only=True)
    slot_count = serializers.IntegerField(source="slot_count", read_only=True)

    class Meta:
        """Serializer configuration for charger summaries."""

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

    def get_health_status(self, obj: Charger) -> str:
        """Compute health status for serialization."""
        return obj.status


class ChargerDetailSerializer(serializers.ModelSerializer):
    """Serialize charger details including slot data."""

    manufacturer_code = serializers.CharField(source="manufacturer.code", read_only=True)
    health_status = serializers.SerializerMethodField(read_only=True)
    is_healthy = serializers.SerializerMethodField(read_only=True)
    slot_count = serializers.IntegerField(source="slot_count", read_only=True)
    slots = ChargerSlotSerializer(many=True, read_only=True)

    class Meta:
        """Serializer configuration for detailed charger payloads."""

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

    def get_health_status(self, obj: Charger) -> str:
        """Compute health status for serialization."""
        return obj.status

    def get_is_healthy(self, obj: Charger) -> bool:
        """Check if charger is healthy for serialization."""
        return obj.status == "online"


class DiscoveredDeviceSerializer(serializers.ModelSerializer):
    """Serialize devices discovered during network scans."""

    type = serializers.CharField(source="device_type", read_only=True)

    class Meta:
        """Serializer configuration for discovered devices."""

        model = DiscoveredDevice
        fields: ClassVar[list[str]] = [
            "ip",
            "type",
            "channels",
            "discovered_at",
        ]


class GroupSerializer(serializers.ModelSerializer):
    """Serialize group metadata for channel organization."""

    group = serializers.SerializerMethodField()

    def get_group(self, obj: Group) -> int:
        """Expose the integer group number as `group`."""
        return int(obj.group_number)

    class Meta:
        """Serializer configuration for groups."""

        model = Group
        fields: ClassVar[list[str]] = [
            "group",
            "group_number",
            "title",
            "slots",
            "hide_charts",
        ]


class DeviceAssignmentSerializer(serializers.ModelSerializer):
    """Serialize device assignment records."""

    class Meta:
        """Serializer configuration for device assignments."""

        model = DeviceAssignment
        fields = "__all__"
