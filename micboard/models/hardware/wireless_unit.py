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

import warnings
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

    def low_battery(self, *, threshold: int = 25) -> WirelessUnitQuerySet:
        """Filter wireless units with battery level below threshold."""
        return self.filter(battery__lt=threshold).exclude(battery=255)


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

    def low_battery(self, *, threshold: int = 25) -> WirelessUnitQuerySet:
        """Filter by low battery."""
        return self.get_queryset().low_battery(threshold=threshold)


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

    # Battery health tracking (from manufacturer API)
    BATTERY_HEALTH_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
        ("critical", "Critical"),
        ("unknown", "Unknown"),
    ]

    battery_health = models.CharField(
        max_length=20,
        blank=True,
        choices=BATTERY_HEALTH_CHOICES,
        help_text="Battery health status from manufacturer API",
    )
    battery_health_description = models.TextField(
        blank=True,
        help_text="Descriptive text for battery health status (from API /battery-health/description)",
    )
    battery_level_description = models.TextField(
        blank=True,
        help_text="Descriptive text for battery level (from API /battery-level/description)",
    )
    battery_cycles = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of battery charge cycles",
    )
    battery_temperature_c = models.FloatField(
        null=True,
        blank=True,
        help_text="Battery temperature in Celsius",
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
        """Get battery level as percentage.

        Deprecated: use wireless_unit_service.get_battery_percentage() instead.
        """
        warnings.warn(
            "WirelessUnit.battery_percentage is deprecated, "
            "use wireless_unit_service.get_battery_percentage(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_battery_percentage

        return get_battery_percentage(self)

    def get_battery_health(self) -> str:
        """Get battery health status.

        Deprecated: use wireless_unit_service.get_battery_health() instead.
        """
        warnings.warn(
            "WirelessUnit.get_battery_health() is deprecated, "
            "use wireless_unit_service.get_battery_health(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_battery_health

        return get_battery_health(self)

    def get_battery_health_display_icon(self) -> str:
        """Get visual icon for battery health.

        Deprecated: use wireless_unit_service.get_battery_health_display_icon() instead.
        """
        warnings.warn(
            "WirelessUnit.get_battery_health_display_icon() is deprecated, "
            "use wireless_unit_service.get_battery_health_display_icon(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_battery_health_display_icon

        return get_battery_health_display_icon(self)

    def is_active_at_time(self, at_time: datetime | None = None) -> bool:
        """Check if unit is active at given time (or now).

        Deprecated: use wireless_unit_service.is_active_at_time() instead.
        """
        warnings.warn(
            "WirelessUnit.is_active_at_time() is deprecated, "
            "use wireless_unit_service.is_active_at_time(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import is_active_at_time

        return is_active_at_time(self, at_time)

    def get_signal_quality(self) -> str:
        """Get signal quality as text.

        Deprecated: use wireless_unit_service.get_signal_quality() instead.
        """
        warnings.warn(
            "WirelessUnit.get_signal_quality() is deprecated, "
            "use wireless_unit_service.get_signal_quality(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_signal_quality

        return get_signal_quality(self)

    def is_transmitter(self) -> bool:
        """Check if this unit transmits microphone audio.

        Deprecated: use wireless_unit_service.is_transmitter() instead.
        """
        warnings.warn(
            "WirelessUnit.is_transmitter() is deprecated, "
            "use wireless_unit_service.is_transmitter(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import is_transmitter

        return is_transmitter(self)

    def get_transmitter_metrics(self) -> dict[str, int | str]:
        """Get transmitter-specific metrics (mic audio, RF level).

        Deprecated: use wireless_unit_service.get_transmitter_metrics() instead.
        """
        warnings.warn(
            "WirelessUnit.get_transmitter_metrics() is deprecated, "
            "use wireless_unit_service.get_transmitter_metrics(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_transmitter_metrics

        return get_transmitter_metrics(self)

    def is_iem_receiver(self) -> bool:
        """Check if this unit receives IEM mix.

        Deprecated: use wireless_unit_service.is_iem_receiver() instead.
        """
        warnings.warn(
            "WirelessUnit.is_iem_receiver() is deprecated, "
            "use wireless_unit_service.is_iem_receiver(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import is_iem_receiver

        return is_iem_receiver(self)

    def get_iem_metrics(self) -> dict[str, int | None]:
        """Get IEM receiver-specific metrics (link quality, mix level).

        Deprecated: use wireless_unit_service.get_iem_metrics() instead.
        """
        warnings.warn(
            "WirelessUnit.get_iem_metrics() is deprecated, "
            "use wireless_unit_service.get_iem_metrics(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_iem_metrics

        return get_iem_metrics(self)

    def get_assigned_rf_channel(self):
        """Get the RFChannel this unit is assigned to, if any.

        Deprecated: use wireless_unit_service.get_assigned_rf_channel() instead.
        """
        warnings.warn(
            "WirelessUnit.get_assigned_rf_channel() is deprecated, "
            "use wireless_unit_service.get_assigned_rf_channel(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_assigned_rf_channel

        return get_assigned_rf_channel(self)

    def get_regulatory_status(self) -> dict[str, str | bool | None]:
        """Get regulatory status by delegating to the assigned RFChannel.

        Deprecated: use wireless_unit_service.get_regulatory_status() instead.
        """
        warnings.warn(
            "WirelessUnit.get_regulatory_status() is deprecated, "
            "use wireless_unit_service.get_regulatory_status(unit) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.hardware.wireless_unit_service import get_regulatory_status

        return get_regulatory_status(self)
