"""WirelessChassis model: Base station/rack unit for wireless audio systems.

Represents the PHYSICAL CHASSIS/RACK UNIT (stationary, rack-mounted hardware with IP/location).
NOT the field devices (wireless units) — those are represented by the WirelessUnit model.

This chassis supports polymorphic RF roles:
  - receiver: Chassis receives RF signals from field wireless units (traditional wireless mics)
             Example: Shure AD4Q receives from 4 field wireless microphones
  - transmitter: Chassis sends IEM mixes to field wireless units (in-ear monitoring)
                Example: Shure PSM sends monitor mixes to performers
  - transceiver: Chassis both receives mic signals AND sends IEM mixes (hybrid bidirectional)
                Example: Sennheiser Spectera Base (64 ch total: 32-in + 32-out)

Each chassis is tied to a manufacturer and model, looked up in device_specifications.yaml
for RFChannel capacity, Dante support, and device capabilities.

Field devices (wireless units: bodypacks, handhelds, IEM receivers) are represented
by the WirelessUnit model
and link back to their host chassis via base_chassis FK.

Architecture & Future-Proofing Notes:
  *** Bidirectional Systems (Sennheiser Spectera model):
      Spectera Base uses WMAS technology to duplexer 64 total channels: 32 RF channels
      receiving mic signals FROM field SEK bodypacks + 32 RF channels sending IEM mixes
      TO the SAME field units (or others). Each SEK is a transceiver simultaneously
      capturing mic audio and playing back IEM. The model handles this via transceiver
      role + bidirectional RF channels with separate metrics for RX/TX.

  *** Multi-Protocol/License-Pool Systems (Shure Axient ANX4 model):
      ANX4 is a receiver that can simultaneously host both Axient Digital AND ULX-D
      wireless units on the same 4 channels. This is handled as a receiver role with
      4 RF channels, where each channel can accept either protocol family at runtime.
      Floating channel licensing (multiple wireless units per RF channel) is tracked
      via WirelessUnit.active statuses and channel_link references.

  *** Future-Proofing:
      New wireless systems should map to existing roles (receiver/transmitter/transceiver)
      and channel directions (receive/send/bidirectional) without requiring code changes.
      Role and direction enums are intentionally manufacturer-agnostic. When adding new
      vendors or models, ask: Is this receiving, transmitting, or both? Does each channel
      have a single direction or multiple? If patterns don't fit, it's a signal to
      revisit the architecture rather than patch with new roles.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet
from micboard.models.device_specs import (
    detect_band_plan_from_api_string,
    get_available_band_plans,
    get_band_plan,
    get_band_plan_from_model_code,
    get_channel_count,
    get_dante_support,
    get_device_role,
    parse_band_plan_from_name,
)


class WirelessChassisQuerySet(TenantOptimizedQuerySet):
    """Enhanced queryset for WirelessChassis model with role and tenant filtering."""

    def active(self) -> WirelessChassisQuerySet:
        """Get all active devices (not offline)."""
        return self.filter(status__in=["online", "degraded", "provisioning"])

    def inactive(self) -> WirelessChassisQuerySet:
        """Get all inactive/offline devices."""
        return self.filter(status="offline")

    def by_status(self, *, status: str) -> WirelessChassisQuerySet:
        """Filter by lifecycle status."""
        return self.filter(status=status)

    def by_role(self, *, role: str) -> WirelessChassisQuerySet:
        """Filter by RF role (receiver/transmitter/transceiver)."""
        return self.filter(role=role)

    def by_manufacturer(self, *, manufacturer: str | int) -> WirelessChassisQuerySet:
        """Filter by manufacturer (code or ID)."""
        if isinstance(manufacturer, str):
            return self.filter(manufacturer__code=manufacturer)
        return self.filter(manufacturer_id=manufacturer)

    def with_channels(self) -> WirelessChassisQuerySet:
        """Optimize: prefetch related RF channels."""
        return self.prefetch_related("rf_channels")


class WirelessChassisManager(TenantOptimizedManager):
    """Enhanced manager for WirelessChassis model with tenant support."""

    def get_queryset(self) -> WirelessChassisQuerySet:
        return WirelessChassisQuerySet(self.model, using=self._db)

    def active(self) -> WirelessChassisQuerySet:
        """Get all active chassis."""
        return self.get_queryset().active()

    def inactive(self) -> WirelessChassisQuerySet:
        """Get all inactive chassis."""
        return self.get_queryset().inactive()

    def by_status(self, *, status: str) -> WirelessChassisQuerySet:
        """Filter by status."""
        return self.get_queryset().by_status(status=status)

    def by_role(self, *, role: str) -> WirelessChassisQuerySet:
        """Filter by RF role."""
        return self.get_queryset().by_role(role=role)

    def by_manufacturer(self, *, manufacturer: str | int) -> WirelessChassisQuerySet:
        """Filter by manufacturer."""
        return self.get_queryset().by_manufacturer(manufacturer=manufacturer)

    def with_channels(self) -> WirelessChassisQuerySet:
        """Optimize with RF channels."""
        return self.get_queryset().with_channels()


class WirelessChassis(models.Model):
    """BASE STATION/RACK UNIT for wireless audio systems (receiver/transmitter/transceiver).

    This model represents the STATIONARY, RACK-MOUNTED chassis hardware.
    NOT the field-side wireless units (which are WirelessUnit model instances).

    The chassis' RF role determines its function:
      - receiver role: Receives RF from field wireless units (traditional wireless mics)
      - transmitter role: Sends IEM mixes to field wireless units
      - transceiver role: Both receive and send (hybrid systems like Sennheiser Spectera)

    Field wireless units link to their host chassis via WirelessUnit.base_chassis FK.
    RFChannel represents RF communication channels/slots on this chassis.
    """

    DEVICE_ROLES: ClassVar[list[tuple[str, str]]] = [
        ("receiver", "Receiver - receives RF from field devices"),
        ("transmitter", "Transmitter - sends IEM mixes to field devices"),
        ("transceiver", "Transceiver - both receive and send (e.g., Spectera)"),
    ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("discovered", "Discovered"),
        ("provisioning", "Provisioning"),
        ("online", "Online"),
        ("degraded", "Degraded"),
        ("offline", "Offline"),
        ("maintenance", "Maintenance"),
        ("retired", "Retired"),
    ]

    # Device role (polymorphic)
    role = models.CharField(
        max_length=20,
        choices=DEVICE_ROLES,
        db_index=True,
        help_text="Device role: receiver, transmitter, or transceiver",
    )

    # Manufacturer and API fields
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="The manufacturer of this device",
    )
    api_device_id = models.CharField(
        max_length=100,
        help_text="Unique identifier from the manufacturer's API",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Device serial number for deduplication",
    )
    mac_address = models.CharField(
        max_length=17,
        blank=True,
        db_index=True,
        help_text="MAC address for hardware-level device identity",
    )

    # Device identification
    model = models.CharField(
        max_length=50,
        blank=True,
        help_text="Full model number (e.g., ULXD4D, Spectera Base)",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Human-readable name for the device",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Device description from API",
    )

    # Protocol/capability metadata
    protocol_family = models.CharField(
        max_length=30,
        default="legacy_uhf",
        help_text=(
            "RF protocol family (e.g., legacy_uhf, axient_digital, ulxd, wmas, iem, spectra)"
        ),
    )
    wmas_capable = models.BooleanField(
        default=False,
        help_text="Whether this chassis supports WMAS/WMAD wideband bidirectional operation",
    )
    licensed_resource_count = models.PositiveIntegerField(
        default=0,
        help_text="Licensed RF resource slots (for license-bound systems like ANX4)",
    )

    # Network configuration
    ip = models.GenericIPAddressField(
        protocol="both",
        unique=True,
        help_text="IP address of the device",
    )
    subnet_mask = models.GenericIPAddressField(
        protocol="both",
        blank=True,
        null=True,
        help_text="Subnet mask",
    )
    gateway = models.GenericIPAddressField(
        protocol="both",
        blank=True,
        null=True,
        help_text="Gateway address",
    )
    network_mode = models.CharField(
        max_length=20,
        blank=True,
        default="auto",
        help_text="Network configuration mode (auto/manual/dhcp/static)",
    )
    interface_id = models.CharField(
        max_length=20,
        blank=True,
        help_text="Network interface identifier",
    )

    # Secondary network interfaces (dual-NIC devices)
    mac_address_secondary = models.CharField(
        max_length=17,
        blank=True,
        help_text="Secondary MAC address (e.g., for Dante)",
    )
    ip_address_secondary = models.GenericIPAddressField(
        protocol="both",
        null=True,
        blank=True,
        help_text="Secondary IP address",
    )

    # Firmware information
    firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Current firmware version",
    )
    hosted_firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Hosted/child device firmware version",
    )

    # Physical location
    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wireless_devices",
        help_text="Physical location of this BASE STATION/RACK UNIT",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order for rack/location layouts",
    )

    # Lifecycle and status
    status = models.CharField(
        max_length=20,
        default="discovered",
        choices=STATUS_CHOICES,
        db_index=True,
        help_text="Current lifecycle status",
    )
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this device was successfully polled",
    )

    # Uptime tracking
    is_online = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Current online status",
    )
    last_online_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When device last came online",
    )
    last_offline_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When device last went offline",
    )
    total_uptime_minutes = models.IntegerField(
        default=0,
        help_text="Cumulative uptime in minutes",
    )

    # Device capabilities (from specification registry)
    max_channels = models.PositiveIntegerField(
        default=4,
        help_text="Maximum number of RF channels for this device",
    )
    dante_capable = models.BooleanField(
        default=False,
        help_text="Whether this device supports Dante audio networking",
    )

    # Frequency band plan (operating range for this chassis)
    band_plan_min_mhz = models.FloatField(
        null=True,
        blank=True,
        help_text="Minimum frequency of this chassis's band plan (MHz) - what it CAN operate on",
    )
    band_plan_max_mhz = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum frequency of this chassis's band plan (MHz) - what it CAN operate on",
    )
    band_plan_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Band plan identifier (e.g., 'UHF Band IV', 'G50 470-534MHz', 'J7 578-608MHz')",
    )

    objects = WirelessChassisManager()

    class Meta:
        verbose_name = "Wireless Chassis"
        verbose_name_plural = "Wireless Chassis"
        ordering: ClassVar[list[str]] = ["order", "manufacturer__name", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["manufacturer", "api_device_id"]),
            models.Index(fields=["role", "status"]),
            models.Index(fields=["serial_number"]),
            models.Index(fields=["mac_address"]),
        ]
        unique_together: ClassVar[list[list[str]]] = [
            ["manufacturer", "api_device_id"],
        ]

    def __str__(self) -> str:
        role_label = dict(self.DEVICE_ROLES).get(self.role, self.role)
        return (
            f"[CHASSIS] {self.manufacturer.name} {self.model} ({role_label}) - "
            f"{self.name} ({self.ip})"
        )

    @property
    def is_out_of_service(self) -> bool:
        """Indicates the chassis is intentionally unavailable for RF service."""
        return self.status in {"maintenance", "retired"}

    def save(self, *args, **kwargs) -> None:
        """Sync specs from device_specifications registry on save."""
        created = self.pk is None

        if self.manufacturer and self.model:
            if hasattr(self.manufacturer, "code"):
                mfg_code = self.manufacturer.code.lower()
            else:
                mfg_code = "unknown"
            self.max_channels = get_channel_count(
                manufacturer=mfg_code,
                model=self.model,
            )
            self.dante_capable = get_dante_support(
                manufacturer=mfg_code,
                model=self.model,
            )

            if not self.role:
                self.role = get_device_role(
                    manufacturer=mfg_code,
                    model=self.model,
                )

        # Auto-populate band plan frequencies when band_plan_name is set
        if self.band_plan_name and self.manufacturer:
            if hasattr(self.manufacturer, "code"):
                mfg_code = self.manufacturer.code.lower()
            else:
                mfg_code = "unknown"

            # Try to look up band plan from registry
            band_key = self.band_plan_name.lower().replace(" ", "_").replace("-", "_")
            band_plan = get_band_plan(manufacturer=mfg_code, band_plan_key=band_key)

            if band_plan:
                # Use registry data
                self.band_plan_min_mhz = band_plan["min_mhz"]
                self.band_plan_max_mhz = band_plan["max_mhz"]
            elif not self.band_plan_min_mhz or not self.band_plan_max_mhz:
                # Try to parse from name string (e.g., "G50 (470-534 MHz)")
                parsed = parse_band_plan_from_name(name=self.band_plan_name)
                if parsed:
                    self.band_plan_min_mhz = parsed["min_mhz"]
                    self.band_plan_max_mhz = parsed["max_mhz"]
        elif not self.band_plan_name and self.manufacturer and self.model:
            # No band plan set - try to detect from model code
            # This captures cases where Shure API doesn't provide frequencyBand
            if hasattr(self.manufacturer, "code"):
                mfg_code = self.manufacturer.code.lower()
                detected = get_band_plan_from_model_code(manufacturer=mfg_code, model=self.model)
                if detected:
                    self.band_plan_name = detected
                    band_plan = get_band_plan(
                        manufacturer=mfg_code,
                        band_plan_key=detected.lower().replace(" ", "_").replace("-", "_"),
                    )
                    if band_plan:
                        self.band_plan_min_mhz = band_plan["min_mhz"]
                        self.band_plan_max_mhz = band_plan["max_mhz"]

        super().save(*args, **kwargs)

        # Handle post-save side effects via service (replacing signals)
        from micboard.services.hardware import HardwareService

        HardwareService.handle_chassis_save(chassis=self, created=created)

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Handle side effects before deletion."""
        from micboard.services.hardware import HardwareService

        HardwareService.handle_chassis_delete(chassis=self)
        return super().delete(*args, **kwargs)

    @property
    def hardware_identity(self) -> dict[str, str]:
        """Get hardware identity for deduplication."""
        return {
            "serial_number": self.serial_number or "",
            "mac_address": self.mac_address or "",
            "api_device_id": self.api_device_id,
        }

    @property
    def network_config(self) -> dict[str, str | None]:
        """Get complete network configuration."""
        return {
            "ip": self.ip,
            "subnet_mask": self.subnet_mask,
            "gateway": self.gateway,
            "mode": self.network_mode,
            "interface_id": self.interface_id,
        }

    @property
    def firmware_info(self) -> dict[str, str]:
        """Get firmware version information."""
        return {
            "device_firmware": self.firmware_version or "Unknown",
            "hosted_firmware": self.hosted_firmware_version or "N/A",
        }

    def is_active_at_time(self, at_time: datetime | None = None) -> bool:
        """Check if device is active at given time (or now)."""
        active_states = {"online", "degraded", "provisioning"}
        return self.status in active_states

    def get_health_status(self) -> str:
        """Compute health status based on status field and last_seen."""
        if self.status == "offline":
            return "offline"
        if self.status in ("maintenance", "retired"):
            return self.status
        if not self.last_seen:
            return "unknown"

        time_since = timezone.now() - self.last_seen
        if time_since < timedelta(minutes=5):
            return "healthy"
        if time_since < timedelta(minutes=30):
            return "warning"
        return "stale"

    def get_expected_channel_count(self) -> int:
        """Get expected number of channels based on device model."""
        return self.max_channels

    def ensure_channel_count(self) -> tuple[int, int]:
        """Create/delete RF channels to match model capacity.

        Returns:
            Tuple of (created_count, deleted_count)
        """
        from micboard.models.rf_coordination import RFChannel

        expected = self.get_expected_channel_count()
        current_channels = set(self.rf_channels.values_list("channel_number", flat=True))
        expected_channels = set(range(1, expected + 1))

        created_count = 0
        deleted_count = 0

        for ch_num in sorted(expected_channels - current_channels):
            if self.role == "receiver":
                link_direction = "receive"
            elif self.role == "transmitter":
                link_direction = "send"
            else:
                link_direction = "bidirectional"

            RFChannel.objects.create(
                chassis=self,
                channel_number=ch_num,
                link_direction=link_direction,
            )
            created_count += 1

        for ch_num in sorted(current_channels - expected_channels):
            self.rf_channels.filter(channel_number=ch_num).delete()
            deleted_count += 1

        return (created_count, deleted_count)

    def get_channels_over_capacity(self):
        """Get RF channels that exceed model capacity."""
        expected = self.get_expected_channel_count()
        return list(self.rf_channels.filter(channel_number__gt=expected))

    def update_device_capabilities(self) -> None:
        """Update capabilities from device specification registry."""
        if not self.manufacturer or not self.model:
            return

        if hasattr(self.manufacturer, "code"):
            mfg_code = self.manufacturer.code.lower()
        else:
            mfg_code = "unknown"
        old_channels = self.max_channels
        old_dante = self.dante_capable
        old_role = self.role

        self.max_channels = get_channel_count(
            manufacturer=mfg_code,
            model=self.model,
        )
        self.dante_capable = get_dante_support(
            manufacturer=mfg_code,
            model=self.model,
        )
        self.role = get_device_role(
            manufacturer=mfg_code,
            model=self.model,
        )

        if (
            old_channels != self.max_channels
            or old_dante != self.dante_capable
            or old_role != self.role
        ):
            self.save(update_fields=["max_channels", "dante_capable", "role"])

    def get_regulatory_domain(self):
        """Get the applicable regulatory domain for this chassis.

        Returns the regulatory domain from:
        1. location.regulatory_domain (if set)
        2. location.country lookup
        3. None if no regulatory info available
        """
        if not self.location:
            return None

        if hasattr(self.location, "regulatory_domain") and self.location.regulatory_domain:
            return self.location.regulatory_domain

        # Try to lookup by country code
        if hasattr(self.location, "country") and self.location.country:
            from micboard.models.rf_coordination import RegulatoryDomain

            return RegulatoryDomain.objects.filter(
                country_code=self.location.country.upper()
            ).first()

        return None

    def has_band_plan(self) -> bool:
        """Check if this chassis has band plan information configured."""
        return (
            self.band_plan_min_mhz is not None
            and self.band_plan_max_mhz is not None
            and self.band_plan_max_mhz > self.band_plan_min_mhz
        )

    def get_available_band_plans(self) -> list[tuple[str, str]]:
        """Get list of available band plans for this chassis's manufacturer.

        Returns:
            List of (key, name) tuples for standard band plans
            Empty list if manufacturer not set or no plans available
        """
        if not self.manufacturer:
            return []

        if hasattr(self.manufacturer, "code"):
            mfg_code = self.manufacturer.code.lower()
        else:
            return []

        return get_available_band_plans(manufacturer=mfg_code)

    def detect_band_plan_from_api_data(
        self, *, api_band_value: str | None
    ) -> dict[str, str | float | None]:
        """Detect band plan from Shure/Sennheiser API frequencyBand value.

        This method is useful when syncing devices from manufacturer APIs that provide
        frequencyBand information. It automatically sets band_plan_name and resolves
        min/max frequencies.

        Example:
            chassis = WirelessChassis(manufacturer=shure_mfg, model="ULXD4Q")
            result = chassis.detect_band_plan_from_api_data(api_band_value="G50")
            # Returns: {
            #   "band_plan_name": "G50 (470-534 MHz)",
            #   "band_plan_min_mhz": 470.0,
            #   "band_plan_max_mhz": 534.0,
            #   "source": "api"
            # }

        Args:
            api_band_value: frequencyBand string from API (e.g., "G50", "G50 (470-534)")

        Returns:
            Dict with detected values and metadata:
            - band_plan_name: Resolved band plan name
            - band_plan_min_mhz: Minimum frequency
            - band_plan_max_mhz: Maximum frequency
            - source: "api" if from API, "model" if inferred from model code
            - message: Human-readable explanation
        """
        if not self.manufacturer:
            return {
                "band_plan_name": None,
                "band_plan_min_mhz": None,
                "band_plan_max_mhz": None,
                "source": None,
                "message": "Manufacturer not set",
            }

        mfg_code = (
            self.manufacturer.code.lower() if hasattr(self.manufacturer, "code") else "unknown"
        )

        # Try API detection first
        if api_band_value:
            detected_name = detect_band_plan_from_api_string(
                api_band_value=api_band_value, manufacturer=mfg_code
            )
            if detected_name:
                band_plan = get_band_plan(
                    manufacturer=mfg_code,
                    band_plan_key=detected_name.lower().replace(" ", "_").replace("-", "_"),
                )
                if band_plan:
                    return {
                        "band_plan_name": detected_name,
                        "band_plan_min_mhz": band_plan["min_mhz"],
                        "band_plan_max_mhz": band_plan["max_mhz"],
                        "source": "api",
                        "message": f"Detected from API frequencyBand '{api_band_value}'",
                    }

        # Fall back to model code detection
        if self.model:
            detected_name = get_band_plan_from_model_code(manufacturer=mfg_code, model=self.model)
            if detected_name:
                band_plan = get_band_plan(
                    manufacturer=mfg_code,
                    band_plan_key=detected_name.lower().replace(" ", "_").replace("-", "_"),
                )
                if band_plan:
                    return {
                        "band_plan_name": detected_name,
                        "band_plan_min_mhz": band_plan["min_mhz"],
                        "band_plan_max_mhz": band_plan["max_mhz"],
                        "source": "model",
                        "message": f"Inferred from model code '{self.model}'",
                    }

        return {
            "band_plan_name": None,
            "band_plan_min_mhz": None,
            "band_plan_max_mhz": None,
            "source": None,
            "message": "No band plan detected from API or model",
        }

    def apply_detected_band_plan(self, *, api_band_value: str | None = None) -> bool:
        """Auto-detect and apply band plan information to this chassis.

        This is a convenience method for device sync workflows that takes the output
        of detect_band_plan_from_api_data() and applies it to the chassis fields.

        Args:
            api_band_value: API frequencyBand value (optional - uses model
                           detection if not provided)

        Returns:
            True if band plan was detected and applied, False otherwise
        """
        detected = self.detect_band_plan_from_api_data(api_band_value=api_band_value)
        if detected.get("band_plan_name"):
            self.band_plan_name = detected["band_plan_name"]
            self.band_plan_min_mhz = detected["band_plan_min_mhz"]
            self.band_plan_max_mhz = detected["band_plan_max_mhz"]
            return True
        return False

    def has_band_plan_regulatory_coverage(self) -> bool:
        """Check if this chassis's band plan has regulatory coverage.

        Returns True if the entire band plan range is covered by regulatory data.
        Returns False if no band plan, no regulatory domain, or insufficient coverage.
        """
        if not self.has_band_plan():
            return False

        domain = self.get_regulatory_domain()
        if not domain:
            return False

        # Check if band plan is within general domain frequency range
        if (
            domain.min_frequency_mhz <= self.band_plan_min_mhz
            and domain.max_frequency_mhz >= self.band_plan_max_mhz
        ):
            return True

        # Check if band plan range overlaps with any allowed/restricted frequency bands
        from micboard.models.rf_coordination import FrequencyBand

        # Find all bands that overlap with this chassis's band plan
        overlapping_bands = FrequencyBand.objects.filter(
            regulatory_domain=domain,
            start_frequency_mhz__lt=self.band_plan_max_mhz,
            end_frequency_mhz__gt=self.band_plan_min_mhz,
        ).exclude(band_type="forbidden")

        if not overlapping_bands.exists():
            return False

        # Check if overlapping bands fully cover the band plan range
        # This is a simplified check - assumes bands are contiguous
        covered_min = min(band.start_frequency_mhz for band in overlapping_bands)
        covered_max = max(band.end_frequency_mhz for band in overlapping_bands)

        return covered_min <= self.band_plan_min_mhz and covered_max >= self.band_plan_max_mhz

    @property
    def needs_band_plan_regulatory_update(self) -> bool:
        """Flag indicating admin needs to update regulatory information for band plan.

        Returns True if:
        - Chassis is online
        - Has a band plan configured
        - But no regulatory coverage exists for that band plan
        """
        if self.status not in ("online", "degraded", "provisioning"):
            return False

        if not self.has_band_plan():
            return False

        return not self.has_band_plan_regulatory_coverage()

    def get_band_plan_regulatory_status(self) -> dict[str, str | bool | None]:
        """Get comprehensive regulatory status for this chassis's band plan.

        Returns dict with:
        - has_band_plan: bool - Whether band plan is configured
        - has_coverage: bool - Whether regulatory data exists for band plan
        - regulatory_domain: str | None - Domain code (e.g., 'FCC', 'ETSI')
        - band_plan_range: str | None - Human-readable band plan range
        - needs_update: bool - Flag for admin attention
        - message: str - Human-readable status message
        """
        domain = self.get_regulatory_domain()
        has_plan = self.has_band_plan()
        has_coverage = self.has_band_plan_regulatory_coverage()

        band_plan_range = None
        if has_plan:
            band_plan_range = f"{self.band_plan_min_mhz}-{self.band_plan_max_mhz} MHz"
            if self.band_plan_name:
                band_plan_range = f"{self.band_plan_name} ({band_plan_range})"

        status = {
            "has_band_plan": has_plan,
            "has_coverage": has_coverage,
            "regulatory_domain": domain.code if domain else None,
            "band_plan_range": band_plan_range,
            "needs_update": self.needs_band_plan_regulatory_update,
        }

        # Generate human-readable message
        if not domain:
            status["message"] = "⚠️ No regulatory domain set for chassis location"
        elif not has_plan:
            status["message"] = "ℹ️ No band plan configured"
        elif not has_coverage:
            status["message"] = (
                f"⚠️ Band plan {band_plan_range} not covered by {domain.code} "
                "regulatory data - admin needs to update"
            )
        else:
            status["message"] = f"✅ Band plan regulatory coverage OK ({domain.code})"

        return status
