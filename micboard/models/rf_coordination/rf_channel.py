"""RFChannel model for directional RF communication channels on a wireless chassis.

Each RF channel represents an RF communication path with direction awareness:
  - receive: Field devices send to chassis (traditional wireless mics)
  - send: Chassis sends to field devices (IEM systems)
  - bidirectional: Both directions (hybrid systems like Sennheiser Spectera)
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit


class RFChannelQuerySet(TenantOptimizedQuerySet):
    """Enhanced queryset for RFChannel model with tenant and direction filtering."""

    def for_user(self, user: User) -> RFChannelQuerySet:
        """Filter RF channels accessible to user via monitoring groups."""
        if user.is_superuser:
            return self

        user_locations = user.monitoring_groups.filter(is_active=True).values_list(
            "monitoringgrouplocation__location", flat=True
        )
        user_all_room_buildings = user.monitoring_groups.filter(
            is_active=True, monitoringgrouplocation__include_all_rooms=True
        ).values_list("monitoringgrouplocation__location__building", flat=True)

        q_objects = Q(chassis__location__in=user_locations)
        if user_all_room_buildings:
            q_objects |= Q(chassis__location__building__in=user_all_room_buildings)

        return self.filter(q_objects).distinct()

    def by_direction(self, *, direction: str) -> RFChannelQuerySet:
        """Filter by link direction (receive/send/bidirectional)."""
        return self.filter(link_direction=direction)

    def receive_links(self) -> RFChannelQuerySet:
        """Get all receive-direction links (field→chassis)."""
        return self.filter(link_direction__in=["receive", "bidirectional"])

    def send_links(self) -> RFChannelQuerySet:
        """Get all send-direction links (chassis→field)."""
        return self.filter(link_direction__in=["send", "bidirectional"])

    def with_chassis(self) -> RFChannelQuerySet:
        """Optimize: select related chassis and location."""
        return self.select_related(
            "chassis",
            "chassis__location",
            "chassis__location__building",
        )

    def with_wireless_unit(self) -> RFChannelQuerySet:
        """Optimize: prefetch related wireless units."""
        return self.prefetch_related("active_wireless_unit")


class RFChannelManager(TenantOptimizedManager):
    """Enhanced manager for RFChannel model with tenant support."""

    def get_queryset(self) -> RFChannelQuerySet:
        return RFChannelQuerySet(self.model, using=self._db)

    def for_user(self, user: User) -> RFChannelQuerySet:
        """Get RF channels accessible to user."""
        return self.get_queryset().for_user(user)

    def by_direction(self, *, direction: str) -> RFChannelQuerySet:
        """Filter by direction."""
        return self.get_queryset().by_direction(direction=direction)

    def receive_links(self) -> RFChannelQuerySet:
        """Get all receive-direction links."""
        return self.get_queryset().receive_links()

    def send_links(self) -> RFChannelQuerySet:
        """Get all send-direction links."""
        return self.get_queryset().send_links()

    def with_chassis(self) -> RFChannelQuerySet:
        """Optimize with chassis and location."""
        return self.get_queryset().with_chassis()

    def with_wireless_unit(self) -> RFChannelQuerySet:
        """Optimize with wireless unit."""
        return self.get_queryset().with_wireless_unit()


class RFChannel(models.Model):
    """Represents a directional RF communication channel on a wireless chassis."""

    LINK_DIRECTIONS: ClassVar[list[tuple[str, str]]] = [
        ("receive", "Receive (field→chassis) - traditional wireless mics"),
        ("send", "Send (chassis→field) - IEM systems"),
        ("bidirectional", "Bidirectional (both) - hybrid/WMAS"),
    ]

    PROTOCOL_FAMILIES: ClassVar[list[tuple[str, str]]] = [
        ("legacy_uhf", "Legacy UHF"),
        ("axient_digital", "Axient Digital"),
        ("ulxd", "ULX-D"),
        ("iem", "IEM"),
        ("spectra", "Spectra / WMAD"),
        ("wmas", "WMAS"),
    ]

    RESOURCE_STATES: ClassVar[list[tuple[str, str]]] = [
        ("free", "Free"),
        ("reserved", "Reserved"),
        ("active", "Active"),
        ("degraded", "Degraded"),
        ("disabled", "Disabled"),
    ]

    chassis = models.ForeignKey(
        WirelessChassis,
        on_delete=models.CASCADE,
        related_name="rf_channels",
        help_text="The wireless chassis this RF channel belongs to",
    )
    channel_number = models.PositiveIntegerField(
        help_text="Channel number on the device",
    )
    link_direction = models.CharField(
        max_length=20,
        choices=LINK_DIRECTIONS,
        default="receive",
        help_text="Direction of RF communication (receive/send/bidirectional)",
    )

    protocol_family = models.CharField(
        max_length=30,
        choices=PROTOCOL_FAMILIES,
        default="legacy_uhf",
        help_text="Protocol family for this RF resource slot",
    )
    wmas_profile = models.CharField(
        max_length=50,
        blank=True,
        help_text="WMAS/WMAD profile or duplex mode when applicable",
    )
    licensed = models.BooleanField(
        default=False,
        help_text="True if this RF resource slot consumes a license",
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Whether this RF resource slot is enabled for use",
    )
    resource_state = models.CharField(
        max_length=20,
        choices=RESOURCE_STATES,
        default="free",
        help_text="Runtime state of the RF resource slot",
    )

    # Receive channel data (field→base)
    frequency = models.FloatField(
        null=True,
        blank=True,
        help_text="Operating frequency for this channel (MHz)",
    )
    rf_signal_strength = models.IntegerField(
        null=True,
        blank=True,
        help_text="Incoming RF signal strength (dB)",
    )
    audio_level = models.IntegerField(
        null=True,
        blank=True,
        help_text="Incoming audio level (dB)",
    )
    signal_quality = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Incoming signal quality indicator (0-255)",
    )
    is_muted = models.BooleanField(
        default=False,
        help_text="Whether this channel is muted",
    )

    active_wireless_unit = models.ForeignKey(
        WirelessUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_on_receive_channels",
        help_text="Currently active wireless unit on this channel (RECEIVE direction)",
    )

    # Send channel data (base→field)
    iem_mix_level = models.IntegerField(
        null=True,
        blank=True,
        help_text="Outgoing IEM mix level (dB) - SEND direction only",
    )
    iem_link_quality = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="IEM receiver link quality (0-255) - SEND direction only",
    )

    active_iem_receiver = models.ForeignKey(
        WirelessUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_on_send_channels",
        help_text="Currently active IEM receiver on this channel (SEND direction)",
    )

    image = models.ImageField(
        upload_to="channel_images/",
        null=True,
        blank=True,
        help_text="Reusable image assigned to this channel",
    )

    objects = RFChannelManager()

    class Meta:
        verbose_name = "RF Channel"
        verbose_name_plural = "RF Channels"
        unique_together: ClassVar[list[list[str]]] = [["chassis", "channel_number"]]
        ordering: ClassVar[list[str]] = ["chassis__name", "channel_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["chassis", "channel_number"]),
            models.Index(fields=["link_direction"]),
        ]

    def __str__(self) -> str:
        direction_label = dict(self.LINK_DIRECTIONS).get(self.link_direction, self.link_direction)
        return f"{self.chassis.name} - RF Ch {self.channel_number} ({direction_label})"

    def save(self, *args, **kwargs) -> None:
        """Validate channel numbering, allowing WMAS chassis to exceed static counts."""
        from django.core.exceptions import ValidationError

        expected_count = self.chassis.get_expected_channel_count()
        if not self.chassis.wmas_capable and self.channel_number > expected_count:
            raise ValidationError(
                f"Channel {self.channel_number} exceeds {self.chassis.model} capacity "
                f"({expected_count} channels max)"
            )
        if self.channel_number < 1:
            raise ValidationError("Channel number must be at least 1")

        super().save(*args, **kwargs)

    def is_receive_channel(self) -> bool:
        """Check if this is a receive-direction channel."""
        return self.link_direction in ("receive", "bidirectional")

    def is_send_channel(self) -> bool:
        """Check if this is a send-direction channel."""
        return self.link_direction in ("send", "bidirectional")

    def get_regulatory_domain(self):
        """Get the applicable regulatory domain for this RF channel.

        Returns the regulatory domain from chassis location or None.
        """
        if not self.chassis or not self.chassis.location:
            return None

        location = self.chassis.location
        if hasattr(location, "regulatory_domain") and location.regulatory_domain:
            return location.regulatory_domain

        # Try to lookup by country code
        if hasattr(location, "country") and location.country:
            from micboard.models.rf_coordination import RegulatoryDomain

            return RegulatoryDomain.objects.filter(country_code=location.country.upper()).first()

        return None

    def has_regulatory_coverage(self) -> bool:
        """Check if this channel's frequency has regulatory data coverage.

        Returns True if frequency is within regulatory domain's allowed bands.
        Returns False if no coverage exists.
        """
        domain = self.get_regulatory_domain()
        if not domain or not self.frequency:
            return False

        # Check if covered by general domain frequency range
        if domain.min_frequency_mhz <= self.frequency <= domain.max_frequency_mhz:
            return True

        # Check if covered by any specific frequency band
        from micboard.models.rf_coordination import FrequencyBand

        return FrequencyBand.objects.filter(
            regulatory_domain=domain,
            start_frequency_mhz__lte=self.frequency,
            end_frequency_mhz__gte=self.frequency,
        ).exists()

    @property
    def needs_regulatory_update(self) -> bool:
        """Flag indicating admin needs to update regulatory information.

        Returns True if channel is active with frequency but no regulatory coverage.
        """
        if self.resource_state not in ("active", "reserved"):
            return False

        if not self.frequency:
            return False

        return not self.has_regulatory_coverage()

    def get_regulatory_status(self) -> dict[str, str | bool | None]:
        """Get comprehensive regulatory status information for admin UI.

        Returns dict with regulatory coverage status and admin action flags.
        """
        domain = self.get_regulatory_domain()
        has_coverage = self.has_regulatory_coverage()

        status = {
            "has_coverage": has_coverage,
            "regulatory_domain": domain.code if domain else None,
            "operating_frequency_mhz": self.frequency,
            "needs_update": self.needs_regulatory_update,
        }

        # Generate human-readable message
        if not domain:
            status["message"] = "⚠️ No regulatory domain set for chassis location"
        elif not self.frequency:
            status["message"] = "ℹ️ No operating frequency configured"
        elif not has_coverage:
            status["message"] = (
                f"⚠️ Frequency {self.frequency} MHz not covered by {domain.code} "
                "regulatory data - admin needs to update"
            )
        else:
            status["message"] = f"✅ Regulatory coverage OK ({domain.code})"

        return status
