"""Lightweight DRF serializers for performer and assignment views."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework import serializers

from micboard.models import (
    DeviceAssignment,
    RFChannel,
    UserProfile,
    WirelessChassis,
)


class UserProfileSerializer(serializers.ModelSerializer):
    """Serialize user profile metadata."""

    class Meta:
        """Profile serializer configuration."""

        model = UserProfile
        fields = ["user_type", "title", "role_description", "photo"]


class PerformerSerializer(serializers.ModelSerializer):
    """Serialize user details alongside profile information."""

    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        """Performer serializer configuration."""

        model = User
        fields = ["id", "username", "full_name", "profile"]


class DeviceAssignmentSerializer(serializers.ModelSerializer):
    """Serialize device assignments with user context."""

    user = PerformerSerializer(read_only=True)

    class Meta:
        """Device assignment serializer configuration."""

        model = DeviceAssignment
        fields = ["id", "user", "channel", "priority", "notes", "is_active"]


class RFChannelSerializer(serializers.ModelSerializer):
    """Serialize RF channels with assignment data."""

    assignments = DeviceAssignmentSerializer(many=True, read_only=True)

    class Meta:
        """RF channel serializer configuration."""

        model = RFChannel
        fields = [
            "id",
            "channel_number",
            "link_direction",
            "frequency",
            "rf_signal_strength",
            "audio_level",
            "assignments",
        ]


class WirelessChassisSerializer(serializers.ModelSerializer):
    """Serialize wireless chassis with nested channels."""

    rf_channels = RFChannelSerializer(many=True, read_only=True)

    class Meta:
        """Wireless chassis serializer configuration."""

        model = WirelessChassis
        fields = [
            "id",
            "name",
            "role",
            "model",
            "ip",
            "is_online",
            "status",
            "rf_channels",
        ]
