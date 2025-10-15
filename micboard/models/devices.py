"""Core device models for the micboard app."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone


class ReceiverQuerySet(models.QuerySet):
    """Custom queryset for Receiver model"""

    def active(self):
        """Get all active receivers"""
        return self.filter(is_active=True)

    def inactive(self):
        """Get all inactive receivers"""
        return self.filter(is_active=False)

    def online_recently(self, minutes=30):
        """Get receivers seen within the last N minutes"""
        threshold = timezone.now() - timedelta(minutes=minutes)
        return self.filter(last_seen__gte=threshold, is_active=True)

    def by_type(self, device_type):
        """Get receivers by device type"""
        return self.filter(device_type=device_type)


class ReceiverManager(models.Manager):
    """Custom manager for Receiver model"""

    def get_queryset(self):
        return ReceiverQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def inactive(self):
        return self.get_queryset().inactive()

    def online_recently(self, minutes=30):
        return self.get_queryset().online_recently(minutes)

    def by_type(self, device_type):
        return self.get_queryset().by_type(device_type)


class Receiver(models.Model):
    """Represents a physical Shure wireless receiver unit."""

    DEVICE_TYPES: ClassVar[list[tuple[str, str]]] = [
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

    objects = ReceiverManager()

    class Meta:
        verbose_name = "Receiver"
        verbose_name_plural = "Receivers"
        ordering: ClassVar[list[str]] = ["name"]
        indexes: ClassVar[list[models.Index]] = [
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

    def get_active_channels(self):
        """Get all channels with active transmitters"""
        return self.channels.filter(transmitter__isnull=False).select_related("transmitter")

    def get_channel_count(self) -> int:
        """Get total number of channels"""
        return self.channels.count()  # type: ignore

    @property
    def health_status(self) -> str:
        """Get health status based on last_seen and is_active"""
        if not self.is_active:
            return "offline"
        if not self.last_seen:
            return "unknown"
        time_since = timezone.now() - self.last_seen
        if time_since < timedelta(minutes=5):
            return "healthy"
        if time_since < timedelta(minutes=30):
            return "warning"
        return "stale"

    @property
    def is_healthy(self) -> bool:
        """Check if receiver is healthy"""
        return self.health_status == "healthy"


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
        unique_together: ClassVar[list[list[str]]] = [["receiver", "channel_number"]]
        ordering: ClassVar[list[str]] = ["receiver__name", "channel_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["receiver", "channel_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.receiver.name} - Channel {self.channel_number}"

    def has_transmitter(self) -> bool:
        """Check if this channel has a transmitter assigned"""
        return hasattr(self, "transmitter")

    def get_transmitter_name(self) -> str:
        """Get transmitter name or empty string"""
        if self.has_transmitter():
            return self.transmitter.name or f"Slot {self.transmitter.slot}"
        return ""


class Transmitter(models.Model):
    # Sentinel values
    UNKNOWN_BYTE_VALUE: ClassVar = 255
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
    battery_charge = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Battery charge percentage (0-100, optional field from newer devices)",
    )
    audio_level = models.IntegerField(default=0, help_text="Audio level in dB")
    rf_level = models.IntegerField(default=0, help_text="RF signal level")
    frequency = models.CharField(max_length=20, blank=True, help_text="Operating frequency")
    antenna = models.CharField(max_length=10, blank=True, help_text="Antenna information")
    tx_offset = models.IntegerField(default=UNKNOWN_BYTE_VALUE, help_text="Transmitter offset")
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
        ordering: ClassVar[list[str]] = ["channel__receiver__name", "channel__channel_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["channel", "slot"]),
        ]

    def __str__(self) -> str:
        return f"Transmitter for {self.channel} (Slot {self.slot})"

    @property
    def battery_percentage(self) -> int | None:
        """Get battery level as percentage"""
        if self.battery == self.UNKNOWN_BYTE_VALUE:
            return None
        return min(100, max(0, self.battery * 100 // self.UNKNOWN_BYTE_VALUE))  # type: ignore

    @property
    def battery_health(self) -> str:
        """Get battery health status"""
        pct = self.battery_percentage
        if pct is None:
            return "unknown"
        if pct > 50:
            return "good"
        if pct > 25:
            return "fair"
        if pct > 10:
            return "low"
        return "critical"

    @property
    def is_active(self) -> bool:
        """Check if transmitter is currently active (recently updated)"""
        if not self.updated_at:
            return False
        time_since = timezone.now() - self.updated_at
        return time_since < timedelta(minutes=5)  # type: ignore

    def get_signal_quality(self) -> str:
        """Get signal quality as text"""
        if self.quality == self.UNKNOWN_BYTE_VALUE:
            return "unknown"
        if self.quality > 200:
            return "excellent"
        if self.quality > 150:
            return "good"
        if self.quality > 100:
            return "fair"
        return "poor"


class TransmitterSession(models.Model):
    """Represents a period where a transmitter is considered active.

    A session starts when we first receive data for a transmitter and ends when
    no data has been received for a configured inactivity threshold.
    """

    transmitter = models.ForeignKey(
        Transmitter,
        on_delete=models.CASCADE,
        related_name="sessions",
        help_text="The transmitter this session belongs to",
    )
    started_at = models.DateTimeField(help_text="When this session started")
    last_seen = models.DateTimeField(help_text="Last time data was seen for this transmitter")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When this session ended")
    is_active = models.BooleanField(
        default=True, help_text="Whether the session is currently active"
    )
    last_status = models.CharField(
        max_length=50, blank=True, help_text="Last known transmitter status"
    )
    sample_count = models.PositiveIntegerField(
        default=0, help_text="Number of samples recorded in this session"
    )

    class Meta:
        verbose_name = "Transmitter Session"
        verbose_name_plural = "Transmitter Sessions"
        ordering: ClassVar[list[str]] = ["-started_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["transmitter", "is_active"]),
            models.Index(fields=["started_at"]),
        ]

    def __str__(self) -> str:
        state = "active" if self.is_active else "ended"
        return f"Session {state} for {self.transmitter} from {self.started_at}"


class TransmitterSample(models.Model):
    """A single data point captured during a transmitter session."""

    session = models.ForeignKey(
        TransmitterSession,
        on_delete=models.CASCADE,
        related_name="samples",
        help_text="The session this sample belongs to",
    )
    timestamp = models.DateTimeField(default=timezone.now, help_text="When the sample was recorded")
    battery = models.PositiveIntegerField(null=True, blank=True)
    battery_charge = models.PositiveIntegerField(null=True, blank=True)
    audio_level = models.IntegerField(null=True, blank=True)
    rf_level = models.IntegerField(null=True, blank=True)
    quality = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, blank=True)
    frequency = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Transmitter Sample"
        verbose_name_plural = "Transmitter Samples"
        ordering: ClassVar[list[str]] = ["-timestamp"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Sample @ {self.timestamp} for {self.session.transmitter}"


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
        ordering: ClassVar[list[str]] = ["group_number"]

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
        ordering: ClassVar[list[str]] = ["key"]

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
        ordering: ClassVar[list[str]] = ["-discovered_at"]

    def __str__(self) -> str:
        return f"{self.device_type} at {self.ip}"
