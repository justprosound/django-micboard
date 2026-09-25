"""RFChannel model for directional RF communication channels on a wireless chassis.

Each RF channel represents an RF communication path with direction awareness:
  - receive: Field devices send to chassis (traditional wireless mics)
  - send: Chassis sends to field devices (IEM systems)
  - bidirectional: Both directions (hybrid systems like Sennheiser Spectera)
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from micboard.models.base_managers import TenantOptimizedQuerySet


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
        "micboard.WirelessChassis",
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
        "micboard.WirelessUnit",
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
        "micboard.WirelessUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_on_send_channels",
        help_text="Currently active IEM receiver on this channel (SEND direction)",
    )

    objects = TenantOptimizedQuerySet.as_manager()

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
