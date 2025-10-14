"""Core device models for the micboard app."""
from __future__ import annotations
from django.db import models
from django.utils import timezone


class Receiver(models.Model):
    """Represents a physical Shure wireless receiver unit."""

    DEVICE_TYPES = [
        ("uhfr", "UHF-R"),
        ("qlxd", "QLX-D"),
        ("ulxd", "ULX-D"),
        ("axtd", "Axient Digital"),
        ("p10t", "P10T"),
        # "offline" is a status, not a type. Removed from here.
    ]

    # Shure System API fields
    api_device_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier from Shure System API",
    )
    ip = models.GenericIPAddressField(protocol="both", help_text="IP address of the device")
    device_type = models.CharField(
        max_length=10, choices=DEVICE_TYPES, help_text="Type of Shure device"
    )
    name = models.CharField(
        max_length=100, blank=True, help_text="Human-readable name for the device"
    )
    firmware_version = models.CharField(
        max_length=50, blank=True, help_text="Firmware version of the device"
    )
    # Status fields
    is_active = models.BooleanField(
        default=True, help_text="Whether this device is currently active/online"
    )
    last_seen = models.DateTimeField(
        null=True, blank=True, help_text="Last time this device was successfully polled"
    )

    class Meta:
        verbose_name = "Receiver"
        verbose_name_plural = "Receivers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["api_device_id"]),
            models.Index(fields=["is_active", "last_seen"]),
        ]

    def __str__(self) -> str:
        return f"{self.device_type} - {self.name} ({self.ip})"

    def mark_online(self) -> None:
        """Mark receiver as online"""
        self.is_active = True
        self.last_seen = timezone.now()
        self.save(update_fields=["is_active", "last_seen"])

    def mark_offline(self) -> None:
        """Mark receiver as offline"""
        self.is_active = False
        self.save(update_fields=["is_active"])


class Channel(models.Model):
    """Represents an individual channel on a Shure wireless receiver."""

    receiver = models.ForeignKey(
        Receiver,
        on_delete=models.CASCADE,
        related_name="channels",
        help_text="The receiver this channel belongs to",
    )
    channel_number = models.PositiveIntegerField(help_text="Channel number on the receiver")

    class Meta:
        verbose_name = "Channel"
        verbose_name_plural = "Channels"
        unique_together = [["receiver", "channel_number"]]
        ordering = ["receiver__name", "channel_number"]
        indexes = [
            models.Index(fields=["receiver", "channel_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.receiver.name} - Channel {self.channel_number}"


class Transmitter(models.Model):
    # Sentinel values
    UNKNOWN_BYTE_VALUE = 255
    """Represents the wireless transmitter data associated with a Channel."""

    channel = models.OneToOneField(
        Channel,
        on_delete=models.CASCADE,
        related_name="transmitter",
        help_text="The channel this transmitter belongs to",
    )
    slot = models.PositiveIntegerField(
        unique=True, help_text="Unique slot number for this channel/transmitter combination"
    )
    # Real-time data from API
    battery = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE, help_text="Battery level (0-255, 255=unknown)"
    )
    audio_level = models.IntegerField(default=0, help_text="Audio level in dB")
    rf_level = models.IntegerField(default=0, help_text="RF signal level")
    frequency = models.CharField(max_length=20, blank=True, help_text="Operating frequency")
    antenna = models.CharField(max_length=10, blank=True, help_text="Antenna information")
    tx_offset = models.IntegerField(
        default=UNKNOWN_BYTE_VALUE, help_text="Transmitter offset"
    )
    quality = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE, help_text="Signal quality (0-255)"
    )
    runtime = models.CharField(max_length=20, blank=True, help_text="Runtime information")
    status = models.CharField(max_length=50, blank=True, help_text="Transmitter status")
    name = models.CharField(max_length=100, blank=True, help_text="Transmitter name")
    name_raw = models.CharField(max_length=100, blank=True, help_text="Raw transmitter name")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Transmitter"
        verbose_name_plural = "Transmitters"
        ordering = ["channel__receiver__name", "channel__channel_number"]
        indexes = [
            models.Index(fields=["channel", "slot"]),
        ]

    def __str__(self) -> str:
        return f"Transmitter for {self.channel} (Slot {self.slot})"

    @property
    def battery_percentage(self) -> int | None:
        """Get battery level as percentage"""
        if self.battery == self.UNKNOWN_BYTE_VALUE:
            return None
        return min(100, max(0, self.battery * 100 // self.UNKNOWN_BYTE_VALUE))


class Group(models.Model):
    """Represents a group of device slots for monitoring"""

    group_number = models.PositiveIntegerField(unique=True, help_text="Unique group number")
    title = models.CharField(max_length=100, help_text="Display title for the group")
    # This 'slots' field will need to be re-evaluated.
    # It currently stores a list of slot numbers.
    # With the new model, it should probably link to Channels or Transmitters.
    slots = models.JSONField(default=list, help_text="List of slot numbers in this group")
    hide_charts = models.BooleanField(
        default=False, help_text="Whether to hide charts for this group"
    )

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"
        ordering = ["group_number"]

    def __str__(self) -> str:
        return f"Group {self.group_number}: {self.title}"

    def get_channels(self):
        """Get all channels in this group"""
        # This method will need to be updated to query the new model structure
        return Transmitter.objects.filter(slot__in=self.slots).select_related(
            "channel", "channel__receiver"
        )


class MicboardConfig(models.Model):
    """Global configuration settings"""

    key = models.CharField(max_length=100, unique=True, help_text="Configuration key")
    value = models.TextField(help_text="Configuration value")

    class Meta:
        verbose_name = "Micboard Configuration"
        verbose_name_plural = "Micboard Configurations"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"


class DiscoveredDevice(models.Model):
    """Represents a device discovered on the network but not yet configured"""

    ip = models.GenericIPAddressField(unique=True, help_text="IP address of the discovered device")
    device_type = models.CharField(max_length=20, help_text="Type of discovered device")
    channels = models.PositiveIntegerField(default=0, help_text="Number of channels on the device")
    discovered_at = models.DateTimeField(
        auto_now_add=True, help_text="When this device was first discovered"
    )

    class Meta:
        verbose_name = "Discovered Device"
        verbose_name_plural = "Discovered Devices"
        ordering = ["-discovered_at"]

    def __str__(self) -> str:
        return f"{self.device_type} at {self.ip}"
