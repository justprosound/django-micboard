"""Factories for discovery-domain models."""

from __future__ import annotations

import factory

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.discovery.discovery_queue import DeviceMovementLog, DiscoveryQueue
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import (
    DiscoveredDevice,
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    MicboardConfig,
)
from tests.factories.base import ProjectModelFactory
from tests.factories.registry import register_factory


@register_factory("micboard.ManufacturerConfiguration")
class ManufacturerConfigurationFactory(ProjectModelFactory):
    """Create a structurally valid manufacturer configuration."""

    class Meta:
        model = ManufacturerConfiguration

    code = factory.Sequence(lambda number: f"manufacturer-config-{number}")
    name = factory.Sequence(lambda number: f"Manufacturer Configuration {number}")


@register_factory("micboard.Manufacturer")
class ManufacturerFactory(ProjectModelFactory):
    """Create an inert, unregistered manufacturer."""

    class Meta:
        model = Manufacturer

    name = factory.Sequence(lambda number: f"Factory Manufacturer {number}")
    code = factory.Sequence(lambda number: f"vendor-{number}")
    config = factory.LazyFunction(lambda: {"source": "factory"})


@register_factory("micboard.DiscoveryQueue")
class DiscoveryQueueFactory(ProjectModelFactory):
    """Create a pending device-discovery review item."""

    class Meta:
        model = DiscoveryQueue

    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    api_device_id = factory.Sequence(lambda number: f"queued-device-{number}")
    ip = factory.Sequence(lambda number: f"2001:db8::{number + 1:x}")
    device_type = "receiver"
    metadata = factory.LazyFunction(lambda: {"source": "factory"})


@register_factory("micboard.DeviceMovementLog")
class DeviceMovementLogFactory(ProjectModelFactory):
    """Create a movement audit record for a chassis."""

    class Meta:
        model = DeviceMovementLog

    device = factory.SubFactory("tests.factories.hardware.WirelessChassisFactory")


@register_factory("micboard.MicboardConfig")
class MicboardConfigFactory(ProjectModelFactory):
    """Create a global configuration entry without discovery side effects."""

    class Meta:
        model = MicboardConfig

    key = factory.Sequence(lambda number: f"factory-config-{number}")
    value = "factory-value"
    manufacturer = None


@register_factory("micboard.DiscoveryCIDR")
class DiscoveryCIDRFactory(ProjectModelFactory):
    """Create a single-address discovery network."""

    class Meta:
        model = DiscoveryCIDR

    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    cidr = factory.Sequence(lambda number: f"2001:db8::{number + 1:x}/128")


@register_factory("micboard.DiscoveryFQDN")
class DiscoveryFQDNFactory(ProjectModelFactory):
    """Create a reserved discovery hostname."""

    class Meta:
        model = DiscoveryFQDN

    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    fqdn = factory.Sequence(lambda number: f"device-{number}.invalid")


@register_factory("micboard.DiscoveryJob")
class DiscoveryJobFactory(ProjectModelFactory):
    """Create a pending discovery job."""

    class Meta:
        model = DiscoveryJob

    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    action = "sync"


@register_factory("micboard.DiscoveredDevice")
class DiscoveredDeviceFactory(ProjectModelFactory):
    """Create a uniquely addressed discovered device."""

    class Meta:
        model = DiscoveredDevice

    ip = factory.Sequence(lambda number: f"2001:db8:1::{number + 1:x}")
    device_type = "receiver"
    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
