"""
Django REST Framework serializers for all core models.

Provides read/write serialization with full relationship support.
"""

from __future__ import annotations

from rest_framework import serializers

from micboard.models import (
    Channel,
    Group,
    Location,
    Manufacturer,
    Receiver,
    Room,
    Transmitter,
)
from micboard.models.configuration import (
    ConfigurationAuditLog,
    ManufacturerConfiguration,
)


class ManufacturerSerializer(serializers.ModelSerializer):
    """Serializer for Manufacturer model."""

    receiver_count = serializers.SerializerMethodField()
    transmitter_count = serializers.SerializerMethodField()
    is_operational = serializers.SerializerMethodField()

    class Meta:
        model = Manufacturer
        fields = [
            "id",
            "code",
            "name",
            "logo_url",
            "website",
            "is_active",
            "created_at",
            "updated_at",
            "receiver_count",
            "transmitter_count",
            "is_operational",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_receiver_count(self, obj: Manufacturer) -> int:
        """Get count of receivers for this manufacturer."""
        return obj.receiver_set.count()

    def get_transmitter_count(self, obj: Manufacturer) -> int:
        """Get count of transmitters for this manufacturer."""
        return obj.transmitter_set.count()

    def get_is_operational(self, obj: Manufacturer) -> bool:
        """Check if manufacturer has any online devices."""
        return (
            obj.receiver_set.filter(is_online=True).exists()
            or obj.transmitter_set.filter(is_online=True).exists()
        )


class ManufacturerDetailSerializer(ManufacturerSerializer):
    """Detailed serializer for Manufacturer with relationships."""

    receivers = serializers.SerializerMethodField()
    transmitters = serializers.SerializerMethodField()

    class Meta(ManufacturerSerializer.Meta):
        fields = ManufacturerSerializer.Meta.fields + ["receivers", "transmitters"]

    def get_receivers(self, obj: Manufacturer) -> list:
        """Get all receivers for this manufacturer."""
        receivers = obj.receiver_set.all()
        return ReceiverListSerializer(receivers, many=True).data

    def get_transmitters(self, obj: Manufacturer) -> list:
        """Get all transmitters for this manufacturer."""
        transmitters = obj.transmitter_set.all()
        return TransmitterListSerializer(transmitters, many=True).data


class ManufacturerConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for ManufacturerConfiguration model."""

    error_count = serializers.SerializerMethodField()
    is_configured = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturerConfiguration
        fields = [
            "id",
            "code",
            "name",
            "is_active",
            "config",
            "is_valid",
            "validation_errors",
            "last_validated",
            "created_at",
            "updated_at",
            "updated_by",
            "error_count",
            "is_configured",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "validation_errors",
            "last_validated",
            "is_valid",
        ]

    def get_error_count(self, obj: ManufacturerConfiguration) -> int:
        """Get count of validation errors."""
        return len(obj.validation_errors.get("errors", []))

    def get_is_configured(self, obj: ManufacturerConfiguration) -> bool:
        """Check if all required config fields are present."""
        required = obj._get_required_fields()
        return all(field in obj.config for field in required)


class ConfigurationAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for ConfigurationAuditLog model."""

    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )
    configuration_code = serializers.CharField(
        source="configuration.code", read_only=True
    )

    class Meta:
        model = ConfigurationAuditLog
        fields = [
            "id",
            "configuration",
            "configuration_code",
            "action",
            "created_by",
            "created_by_name",
            "created_at",
            "old_values",
            "new_values",
            "result",
            "error_message",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "created_by",
            "created_by_name",
            "configuration_code",
        ]


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for Location model."""

    room_count = serializers.SerializerMethodField()
    device_count = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = [
            "id",
            "name",
            "building",
            "floor",
            "description",
            "created_at",
            "updated_at",
            "room_count",
            "device_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_room_count(self, obj: Location) -> int:
        """Get count of rooms in this location."""
        return obj.room_set.count()

    def get_device_count(self, obj: Location) -> int:
        """Get count of devices assigned to this location."""
        return (
            obj.deviceassignment_set.filter(
                device_content_type__model__in=["receiver", "transmitter"]
            ).count()
        )


class RoomSerializer(serializers.ModelSerializer):
    """Serializer for Room model."""

    location_name = serializers.CharField(source="location.name", read_only=True)
    device_count = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "name",
            "location",
            "location_name",
            "capacity",
            "description",
            "created_at",
            "updated_at",
            "device_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_device_count(self, obj: Room) -> int:
        """Get count of devices in this room."""
        return (
            obj.deviceassignment_set.filter(
                device_content_type__model__in=["receiver", "transmitter"]
            ).count()
        )


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Group model."""

    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "description",
            "created_at",
            "updated_at",
            "member_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_member_count(self, obj: Group) -> int:
        """Get count of devices in this group."""
        return obj.members.count()


class ChannelSerializer(serializers.ModelSerializer):
    """Serializer for Channel model."""

    class Meta:
        model = Channel
        fields = [
            "id",
            "receiver",
            "number",
            "name",
            "frequency",
            "rf_level",
            "audio_level",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChannelDetailSerializer(ChannelSerializer):
    """Detailed serializer for Channel."""

    receiver_name = serializers.CharField(source="receiver.name", read_only=True)
    receiver_model = serializers.CharField(source="receiver.model", read_only=True)

    class Meta(ChannelSerializer.Meta):
        fields = ChannelSerializer.Meta.fields + ["receiver_name", "receiver_model"]


class ReceiverListSerializer(serializers.ModelSerializer):
    """List serializer for Receiver (minimal fields)."""

    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True
    )
    online_channels = serializers.SerializerMethodField()

    class Meta:
        model = Receiver
        fields = [
            "id",
            "name",
            "model",
            "manufacturer",
            "manufacturer_name",
            "ip_address",
            "is_online",
            "online_channels",
            "battery_level",
        ]
        read_only_fields = ["id"]

    def get_online_channels(self, obj: Receiver) -> int:
        """Get count of online channels."""
        return obj.channel_set.filter(is_active=True).count()


class ReceiverSerializer(serializers.ModelSerializer):
    """Serializer for Receiver model."""

    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True
    )
    channel_count = serializers.SerializerMethodField()
    signal_strength = serializers.SerializerMethodField()

    class Meta:
        model = Receiver
        fields = [
            "id",
            "name",
            "model",
            "manufacturer",
            "manufacturer_name",
            "ip_address",
            "hostname",
            "mac_address",
            "firmware_version",
            "is_online",
            "battery_level",
            "frequency_range",
            "max_channels",
            "created_at",
            "updated_at",
            "channel_count",
            "signal_strength",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_channel_count(self, obj: Receiver) -> int:
        """Get count of channels."""
        return obj.channel_set.count()

    def get_signal_strength(self, obj: Receiver) -> float | None:
        """Get average signal strength across channels."""
        channels = obj.channel_set.exclude(rf_level__isnull=True)
        if not channels.exists():
            return None
        return sum(c.rf_level for c in channels) / channels.count()


class ReceiverDetailSerializer(ReceiverSerializer):
    """Detailed serializer for Receiver with channels."""

    channels = ChannelDetailSerializer(
        source="channel_set", many=True, read_only=True
    )

    class Meta(ReceiverSerializer.Meta):
        fields = ReceiverSerializer.Meta.fields + ["channels"]


class TransmitterListSerializer(serializers.ModelSerializer):
    """List serializer for Transmitter (minimal fields)."""

    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True
    )

    class Meta:
        model = Transmitter
        fields = [
            "id",
            "name",
            "model",
            "manufacturer",
            "manufacturer_name",
            "is_online",
            "battery_level",
            "frequency",
        ]
        read_only_fields = ["id"]


class TransmitterSerializer(serializers.ModelSerializer):
    """Serializer for Transmitter model."""

    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True
    )

    class Meta:
        model = Transmitter
        fields = [
            "id",
            "name",
            "model",
            "manufacturer",
            "manufacturer_name",
            "ip_address",
            "hostname",
            "mac_address",
            "firmware_version",
            "is_online",
            "battery_level",
            "battery_type",
            "frequency",
            "rf_level",
            "audio_level",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TransmitterDetailSerializer(TransmitterSerializer):
    """Detailed serializer for Transmitter."""

    pass


# Bulk operation serializers


class BulkDeviceActionSerializer(serializers.Serializer):
    """Serializer for bulk device operations."""

    device_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of device IDs",
    )
    action = serializers.ChoiceField(
        choices=[
            "activate",
            "deactivate",
            "reboot",
            "sync",
            "group",
            "ungroup",
        ],
        help_text="Action to perform",
    )
    group_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Group ID for group/ungroup actions",
    )


class HealthStatusSerializer(serializers.Serializer):
    """Serializer for service health status."""

    code = serializers.CharField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=["healthy", "degraded", "unhealthy"])
    message = serializers.CharField(allow_blank=True)
    device_count = serializers.IntegerField(min_value=0)
    online_count = serializers.IntegerField(min_value=0)
    last_poll = serializers.DateTimeField(allow_null=True)
    error_count = serializers.IntegerField(min_value=0)
