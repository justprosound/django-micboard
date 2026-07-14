"""Factories for telemetry-domain models."""

from __future__ import annotations

from django.utils import timezone

import factory

from micboard.models.telemetry.health import APIHealthLog
from micboard.models.telemetry.sessions import WirelessUnitSample, WirelessUnitSession
from tests.factories.base import ProjectModelFactory
from tests.factories.registry import register_factory


@register_factory("micboard.APIHealthLog")
class APIHealthLogFactory(ProjectModelFactory):
    """Create a healthy manufacturer API observation."""

    class Meta:
        model = APIHealthLog

    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    timestamp = factory.LazyFunction(timezone.now)
    status = "healthy"
    details = factory.LazyFunction(lambda: {"source": "factory"})


@register_factory("micboard.WirelessUnitSession")
class WirelessUnitSessionFactory(ProjectModelFactory):
    """Create an active telemetry session for a wireless unit."""

    class Meta:
        model = WirelessUnitSession

    wireless_unit = factory.SubFactory("tests.factories.hardware.WirelessUnitFactory")
    started_at = factory.LazyFunction(timezone.now)
    last_seen = factory.LazyFunction(timezone.now)


@register_factory("micboard.WirelessUnitSample")
class WirelessUnitSampleFactory(ProjectModelFactory):
    """Create a telemetry sample attached to an active session."""

    class Meta:
        model = WirelessUnitSample

    session = factory.SubFactory("tests.factories.telemetry.WirelessUnitSessionFactory")
    timestamp = factory.LazyFunction(timezone.now)
