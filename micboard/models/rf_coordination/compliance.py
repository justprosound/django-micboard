"""Regulatory compliance models for RF coordination.

Provides models to track regulatory domains (FCC, ETSI), excluded frequency ranges,
and compliance rules for specific locations.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class RegulatoryDomain(models.Model):
    """Regulatory body or region governing RF spectrum usage (e.g., FCC, ETSI)."""

    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Regulatory code (e.g., 'FCC', 'ETSI', 'JAPAN')",
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g., 'US', 'DE', 'AU')",
    )
    name = models.CharField(
        max_length=100,
        help_text="Full name (e.g., 'Federal Communications Commission')",
    )
    description = models.TextField(blank=True)

    # Frequency ranges allowed for wireless audio in this domain (Global bounds)
    min_frequency_mhz = models.FloatField(
        default=470.0,
        help_text="Minimum allowed frequency in MHz",
    )
    max_frequency_mhz = models.FloatField(
        default=608.0,
        help_text="Maximum allowed frequency in MHz",
    )

    class Meta:
        verbose_name = "Regulatory Domain"
        verbose_name_plural = "Regulatory Domains"
        ordering: ClassVar[list[str]] = ["code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"


class FrequencyBand(models.Model):
    """Specific frequency band within a regulatory domain."""

    BAND_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("allowed", "Allowed (General Use)"),
        ("restricted", "Restricted (License Required)"),
        ("forbidden", "Forbidden (Blocked)"),
        ("guard", "Guard Band"),
    ]

    regulatory_domain = models.ForeignKey(
        RegulatoryDomain,
        on_delete=models.CASCADE,
        related_name="frequency_bands",
        help_text="The regulatory domain this band belongs to",
    )
    name = models.CharField(
        max_length=100,
        help_text="Band name (e.g., 'Duplex Gap', '600MHz Guard Band')",
    )
    start_frequency_mhz = models.FloatField(help_text="Start frequency in MHz")
    end_frequency_mhz = models.FloatField(help_text="End frequency in MHz")

    band_type = models.CharField(
        max_length=20,
        choices=BAND_TYPES,
        default="allowed",
        help_text="Regulatory status of this band",
    )

    power_limit_mw = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max allowed power in mW (ERP/EIRP) if applicable",
    )

    duty_cycle = models.FloatField(
        null=True,
        blank=True,
        help_text="Max duty cycle % (e.g. 100.0 for continuous)",
    )

    channel_bandwidth_khz = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Standard channel bandwidth in kHz",
    )

    licensing_info = models.TextField(
        blank=True,
        help_text="Advisory information regarding licensing requirements.",
    )

    fee_structure = models.CharField(
        max_length=255,
        blank=True,
        help_text="Advisory information regarding fees.",
    )

    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Frequency Band"
        verbose_name_plural = "Frequency Bands"
        ordering: ClassVar[list[str]] = ["start_frequency_mhz"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["regulatory_domain", "start_frequency_mhz"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.regulatory_domain.code} - {self.name} "
            f"({self.start_frequency_mhz}-{self.end_frequency_mhz} MHz)"
        )


class ExclusionZone(models.Model):
    """Geo-fenced area with specific frequency exclusions (e.g., near TV towers)."""

    name = models.CharField(max_length=100)
    regulatory_domain = models.ForeignKey(
        RegulatoryDomain,
        on_delete=models.CASCADE,
        related_name="exclusion_zones",
        null=True,
        blank=True,
        help_text="Regulatory domain (optional, if tied to a specific domain)",
    )

    # Geo-fencing (simple circular)
    latitude = models.FloatField(help_text="Latitude of the zone center")
    longitude = models.FloatField(help_text="Longitude of the zone center")
    radius_km = models.FloatField(default=1.0, help_text="Radius of the zone in kilometers")

    # Excluded frequency range
    start_frequency_mhz = models.FloatField(help_text="Start of excluded frequency range")
    end_frequency_mhz = models.FloatField(help_text="End of excluded frequency range")

    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for exclusion (e.g., 'TV Channel 38')",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Exclusion Zone"
        verbose_name_plural = "Exclusion Zones"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_frequency_mhz}-{self.end_frequency_mhz} MHz)"
