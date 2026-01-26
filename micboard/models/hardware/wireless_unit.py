"""WirelessUnit model for field wireless audio devices.

Represents field-side wireless devices (bodypacks, handheld, IEM receivers, etc.)
with awareness of device type:
  - mic_transmitter: Sends mic audio to chassis (traditional wireless mics)
  - iem_receiver: Receives IEM mix from chassis (in-ear monitoring)
  - transceiver: Both send mic and receive IEM (e.g., Sennheiser Spectera SEK)

Tracks battery levels, RF quality, link quality, and device state.
Links to WirelessChassis base unit and RFChannel for RF path tracking.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet


class WirelessUnitQuerySet(TenantOptimizedQuerySet):
    """Enhanced queryset for WirelessUnit model with tenant filtering."""

    def active(self) -> WirelessUnitQuerySet:
        """Get all active wireless units."""
        active_states = ["online", "degraded", "provisioning"]
        threshold = timezone.now() - timedelta(minutes=5)
        return self.filter(status__in=active_states, last_seen__gte=threshold)

    def by_status(self, *, status: str) -> WirelessUnitQuerySet:
        """Filter by lifecycle status."""
        return self.filter(status=status)

    def by_type(self, *, device_type: str) -> WirelessUnitQuerySet:
        """Filter by wireless unit device type."""
        return self.filter(device_type=device_type)

    def by_base_device(self, *, device_id: int) -> WirelessUnitQuerySet:
        """Filter wireless units by base chassis ID."""
        return self.filter(base_chassis_id=device_id)

    def low_battery(self, *, threshold: int = 25) -> WirelessUnitQuerySet:
        """Filter wireless units with battery level below threshold."""
        return self.filter(battery__lt=threshold).exclude(battery=255)

    def with_base_device(self) -> WirelessUnitQuerySet:
        """Optimize: select related base device."""
        return self.select_related("base_chassis", "base_chassis__location")


class WirelessUnitManager(TenantOptimizedManager):
    """Enhanced manager for WirelessUnit model with tenant support."""

    def get_queryset(self) -> WirelessUnitQuerySet:
        return WirelessUnitQuerySet(self.model, using=self._db)

    def active(self) -> WirelessUnitQuerySet:
        """Get all active wireless units."""
        return self.get_queryset().active()

    def by_status(self, *, status: str) -> WirelessUnitQuerySet:
        """Filter by status."""
        return self.get_queryset().by_status(status=status)

    def by_type(self, *, device_type: str) -> WirelessUnitQuerySet:
        """Filter by device type."""
        return self.get_queryset().by_type(device_type=device_type)

    def by_base_device(self, *, device_id: int) -> WirelessUnitQuerySet:
        """Filter by base chassis."""
        return self.get_queryset().by_base_device(device_id=device_id)

    def low_battery(self, *, threshold: int = 25) -> WirelessUnitQuerySet:
        """Filter by low battery."""
        return self.get_queryset().low_battery(threshold=threshold)

    def with_base_device(self) -> WirelessUnitQuerySet:
        """Optimize with base device."""
        return self.get_queryset().with_base_device()


class WirelessUnit(models.Model):
    """Field-side wireless audio device (bodypack, handheld, IEM receiver, etc.)."""

    UNKNOWN_BYTE_VALUE: ClassVar = 255

    DEVICE_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("mic_transmitter", "Microphone Transmitter - sends mic to base"),
        ("iem_receiver", "IEM Receiver - receives mix from base"),
        ("transceiver", "Transceiver - sends mic AND receives IEM"),
    ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("discovered", "Discovered"),
        ("provisioning", "Provisioning"),
        ("online", "Online"),
        ("degraded", "Degraded"),
        ("idle", "Idle"),
        ("offline", "Offline"),
        ("maintenance", "Maintenance"),
        ("retired", "Retired"),
    ]

    device_type = models.CharField(
        max_length=20,
        choices=DEVICE_TYPES,
        default="mic_transmitter",
        db_index=True,
        help_text="Type of field device: mic_transmitter, iem_receiver, or transceiver",
    )

    base_chassis = models.ForeignKey(
        "micboard.WirelessChassis",
        on_delete=models.CASCADE,
        related_name="field_units",
        help_text="The base station this unit is paired with",
    )

    protocol_family = models.CharField(
        max_length=30,
        default="legacy_uhf",
        help_text=(
            "RF protocol family (e.g., legacy_uhf, axient_digital, ulxd, wmas, iem, spectra)"
        ),
    )
    wmas_profile = models.CharField(
        max_length=50,
        blank=True,
        help_text="WMAS/WMAD profile or duplex mode when applicable",
    )
    assigned_resource = models.ForeignKey(
        "micboard.RFChannel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_units",
        help_text="RF resource slot this unit is currently using (if any)",
    )

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="The manufacturer of this field unit",
    )
    model = models.CharField(
        max_length=50,
        blank=True,
        help_text="Field unit model (e.g., ULXD2, SEK)",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Field unit serial number for tracking",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Field unit name (e.g., 'Lead Vocalist', 'Monitor 1')",
    )

    slot = models.PositiveIntegerField(
        db_index=True,
        help_text="Slot number on the base device",
    )

    # Battery
    battery = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE,
        help_text="Battery level (0-255, 255=unknown)",
    )
    battery_charge = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Battery charge percentage (0-100)",
    )
    battery_runtime = models.CharField(
        max_length=20,
        blank=True,
        help_text="Estimated battery runtime (e.g., '4:30:00')",
    )
    battery_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Battery type (e.g., 'Lithium-Ion', 'AA Alkaline')",
    )

    # Transmitter metrics (mic_transmitter / transceiver)
    audio_level = models.IntegerField(
        default=0,
        help_text="Microphone audio level (dB)",
    )
    rf_level = models.IntegerField(
        default=0,
        help_text="Transmitter RF signal level",
    )
    frequency = models.CharField(
        max_length=20,
        blank=True,
        help_text="Operating frequency (MHz)",
    )
    antenna = models.CharField(
        max_length=10,
        blank=True,
        help_text="Antenna information",
    )
    tx_offset = models.IntegerField(
        default=UNKNOWN_BYTE_VALUE,
        help_text="Transmitter offset",
    )
    quality = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE,
        help_text="Signal quality (0-255)",
    )

    # IEM receiver metrics (iem_receiver / transceiver)
    iem_link_quality = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="IEM receiver link quality (0-255)",
    )
    iem_audio_level = models.IntegerField(
        null=True,
        blank=True,
        help_text="IEM audio level received (dB)",
    )

    # State
    firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Field unit firmware version",
    )
    status = models.CharField(
        max_length=20,
        default="discovered",
        choices=STATUS_CHOICES,
        db_index=True,
        help_text="Current lifecycle status",
    )
    api_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="Status from manufacturer API",
    )
    charging_status = models.BooleanField(
        default=False,
        help_text="Whether the unit is currently charging",
    )
    is_muted = models.BooleanField(
        default=False,
        help_text="Whether transmitter audio is muted",
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this unit was successfully polled",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp",
    )

    objects = WirelessUnitManager()

    class Meta:
        verbose_name = "Wireless Unit (Field Device)"
        verbose_name_plural = "Wireless Units (Field Devices)"
        ordering: ClassVar[list[str]] = ["base_chassis__name", "slot"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["base_chassis", "slot"]),
            models.Index(fields=["serial_number"]),
            models.Index(fields=["status", "last_seen"]),
            models.Index(fields=["device_type"]),
        ]

    def __str__(self) -> str:
        device_type_label = dict(self.DEVICE_TYPES).get(self.device_type, self.device_type)
        if self.name:
            return f"{self.name} ({device_type_label}) - Slot {self.slot}"
        return f"Unit {self.serial_number} - {device_type_label} (Slot {self.slot})"

    @property
    def battery_percentage(self) -> int | None:
        """Get battery level as percentage."""
        if self.battery == self.UNKNOWN_BYTE_VALUE:
            return None
        return min(100, max(0, self.battery * 100 // self.UNKNOWN_BYTE_VALUE))

    def get_battery_health(self) -> str:
        """Compute battery health status from percentage."""
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

    def is_active_at_time(self, at_time: datetime | None = None) -> bool:
        """Check if unit is active at given time (or now)."""
        check_time = at_time or timezone.now()
        active_states = ["online", "degraded", "provisioning"]
        if self.status not in active_states:
            return False

        ref_time = self.last_seen or self.updated_at
        if not ref_time:
            return False

        time_since = check_time - ref_time
        return time_since < timedelta(minutes=5)

    def get_signal_quality(self) -> str:
        """Get signal quality as text."""
        if self.quality == self.UNKNOWN_BYTE_VALUE:
            return "unknown"
        if self.quality > 200:
            return "excellent"
        if self.quality > 150:
            return "good"
        if self.quality > 100:
            return "fair"
        return "poor"

    @property
    def is_idle(self) -> bool:
        """Indicates the portable is unused/not engaged on any RF resource."""
        return self.status == "idle" or (
            self.assigned_resource is None and self.status in {"offline", "degraded"}
        )

    def is_transmitter(self) -> bool:
        """Check if this unit transmits microphone audio."""
        return self.device_type in ("mic_transmitter", "transceiver")

    def get_transmitter_metrics(self) -> dict[str, int | str]:
        """Get transmitter-specific metrics (mic audio, RF level)."""
        if not self.is_transmitter():
            return {}
        return {
            "audio_level": self.audio_level,
            "rf_level": self.rf_level,
            "quality": self.get_signal_quality(),
            "frequency": self.frequency,
        }

    def is_iem_receiver(self) -> bool:
        """Check if this unit receives IEM mix."""
        return self.device_type in ("iem_receiver", "transceiver")

    def get_iem_metrics(self) -> dict[str, int | None]:
        """Get IEM receiver-specific metrics (link quality, mix level)."""
        if not self.is_iem_receiver():
            return {}
        return {
            "iem_link_quality": self.iem_link_quality,
            "iem_audio_level": self.iem_audio_level,
        }

    def get_assigned_rf_channel(self):
        """Get the RFChannel this unit is assigned to, if any.

        Note: RF coordination happens at the RFChannel level, not WirelessUnit level.
        This unit's frequency field is just a reported value from the device.
        For regulatory checks, use RFChannel.get_regulatory_status() instead.
        """
        # Check if this unit is active on any receive channel
        if hasattr(self, "active_on_receive_channels"):
            return self.active_on_receive_channels.first()

        # Check if linked via assigned_resource (if that field exists)
        if hasattr(self, "assigned_resource") and self.assigned_resource:
            return self.assigned_resource

        return None

    def get_regulatory_status(self) -> dict[str, str | bool | None]:
        """Get regulatory status by delegating to the assigned RFChannel.

        Note: Actual RF coordination and regulatory compliance happens at RFChannel level.
        This method is a convenience wrapper that delegates to the assigned channel.

        Returns dict with:
        - has_coverage: bool
        - regulatory_domain: str | None
        - operating_frequency_mhz: float | None
        - needs_update: bool
        - message: str
        - source: str - Indicates this came from RFChannel delegation
        """
        rf_channel = self.get_assigned_rf_channel()

        if rf_channel:
            status = rf_channel.get_regulatory_status()
            status["source"] = "rf_channel"
            status["message"] = f"Via RFChannel {rf_channel.channel_number}: {status['message']}"
            return status

        # No RF channel assigned - return basic status
        return {
            "has_coverage": False,
            "regulatory_domain": None,
            "operating_frequency_mhz": None,
            "needs_update": False,
            "source": "no_channel",
            "message": "ℹ️ No RF channel assigned - regulatory check not applicable",
        }
