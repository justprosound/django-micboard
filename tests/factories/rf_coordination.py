"""Factories for RF coordination and regulatory models."""

from __future__ import annotations

import factory

from micboard.models.rf_coordination.compliance import (
    ExclusionZone,
    FrequencyBand,
    RegulatoryDomain,
)
from micboard.models.rf_coordination.rf_channel import RFChannel

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.RegulatoryDomain")
class RegulatoryDomainFactory(ProjectModelFactory):
    """Create a unique regulatory domain with a valid frequency range."""

    class Meta:
        model = RegulatoryDomain

    code = factory.Sequence(lambda number: f"REG-{number}")
    name = factory.Sequence(lambda number: f"Regulatory Domain {number}")
    country_code = "ZZ"
    min_frequency_mhz = 470.0
    max_frequency_mhz = 608.0


@register_factory("micboard.FrequencyBand")
class FrequencyBandFactory(ProjectModelFactory):
    """Create an allowed band within its regulatory domain."""

    class Meta:
        model = FrequencyBand

    regulatory_domain = factory.SubFactory(
        "tests.factories.rf_coordination.RegulatoryDomainFactory"
    )
    name = factory.Sequence(lambda number: f"Frequency Band {number}")
    start_frequency_mhz = 470.0
    end_frequency_mhz = 608.0
    band_type = "allowed"


@register_factory("micboard.ExclusionZone")
class ExclusionZoneFactory(ProjectModelFactory):
    """Create an active exclusion zone with deterministic geometry."""

    class Meta:
        model = ExclusionZone

    name = factory.Sequence(lambda number: f"Exclusion Zone {number}")
    regulatory_domain = factory.SubFactory(
        "tests.factories.rf_coordination.RegulatoryDomainFactory"
    )
    latitude = 33.7756
    longitude = -84.3963
    radius_km = 1.0
    start_frequency_mhz = 500.0
    end_frequency_mhz = 501.0


@register_factory("micboard.RFChannel")
class RFChannelFactory(ProjectModelFactory):
    """Create a channel on a neutral WMAS-capable chassis."""

    class Meta:
        model = RFChannel

    chassis = factory.SubFactory(
        "tests.factories.hardware.WirelessChassisFactory",
        max_channels=0,
        wmas_capable=True,
    )
    channel_number = factory.Sequence(lambda number: number + 1)
    link_direction = "receive"
    protocol_family = "legacy_uhf"
    resource_state = "free"
