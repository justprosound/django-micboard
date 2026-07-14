"""Factories for hardware and integration inventory models."""

from __future__ import annotations

import factory

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.integrations import Accessory, ManufacturerAPIServer

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.Charger")
class ChargerFactory(ProjectModelFactory):
    """Create a charger at a valid physical location."""

    class Meta:
        model = Charger

    location = factory.SubFactory("tests.factories.locations.LocationFactory")
    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    model = "Factory Charger"
    serial_number = factory.Sequence(lambda number: f"charger-serial-{number}")
    name = factory.Sequence(lambda number: f"Charger {number}")
    ip = factory.Sequence(lambda number: f"2001:db8:1::{number + 1}")
    status = "discovered"


@register_factory("micboard.ChargerSlot")
class ChargerSlotFactory(ProjectModelFactory):
    """Create an empty slot on a unique charger."""

    class Meta:
        model = ChargerSlot

    charger = factory.SubFactory("tests.factories.hardware.ChargerFactory")
    slot_number = 1
    occupied = False


@register_factory("micboard.DisplayWall")
class DisplayWallFactory(ProjectModelFactory):
    """Create a display wall with a unique kiosk identity."""

    class Meta:
        model = DisplayWall

    location = factory.SubFactory("tests.factories.locations.LocationFactory")
    name = factory.Sequence(lambda number: f"Display Wall {number}")
    kiosk_id = factory.Sequence(lambda number: f"kiosk-{number}")


@register_factory("micboard.WallSection")
class WallSectionFactory(ProjectModelFactory):
    """Create an unassigned section on a display wall."""

    class Meta:
        model = WallSection

    wall = factory.SubFactory("tests.factories.hardware.DisplayWallFactory")
    name = factory.Sequence(lambda number: f"Section {number}")


@register_factory("micboard.WirelessChassis")
class WirelessChassisFactory(ProjectModelFactory):
    """Create a neutral chassis without provisioning RF channels."""

    class Meta:
        model = WirelessChassis

    role = "receiver"
    manufacturer = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    api_device_id = factory.Sequence(lambda number: f"factory-chassis-{number}")
    serial_number = factory.Sequence(lambda number: f"chassis-serial-{number}")
    name = factory.Sequence(lambda number: f"Wireless Chassis {number}")
    ip = factory.Sequence(lambda number: f"2001:db8:2::{number + 1}")
    status = "discovered"
    max_channels = 0


@register_factory("micboard.WirelessUnit")
class WirelessUnitFactory(ProjectModelFactory):
    """Create a field unit whose manufacturer matches its chassis."""

    class Meta:
        model = WirelessUnit

    base_chassis = factory.SubFactory(
        "tests.factories.hardware.WirelessChassisFactory",
        max_channels=1,
    )
    manufacturer = factory.SelfAttribute("base_chassis.manufacturer")
    serial_number = factory.Sequence(lambda number: f"unit-serial-{number}")
    name = factory.Sequence(lambda number: f"Wireless Unit {number}")
    slot = 1
    status = "discovered"


@register_factory("micboard.ManufacturerAPIServer")
class ManufacturerAPIServerFactory(ProjectModelFactory):
    """Create a valid, isolated manufacturer service endpoint."""

    class Meta:
        model = ManufacturerAPIServer

    name = factory.Sequence(lambda number: f"Manufacturer Server {number}")
    manufacturer = ManufacturerAPIServer.Manufacturer.OTHER
    base_url = factory.Sequence(lambda number: f"https://api-{number}.example.test")
    shared_key = factory.Sequence(lambda number: f"factory-shared-key-{number}")
    status = ManufacturerAPIServer.Status.UNKNOWN


@register_factory("micboard.Accessory")
class AccessoryFactory(ProjectModelFactory):
    """Create a uniquely tracked accessory assigned to a chassis."""

    class Meta:
        model = Accessory

    name = factory.Sequence(lambda number: f"Accessory {number}")
    sku = factory.Sequence(lambda number: f"SKU-{number}")
    category = Accessory.Category.OTHER
    chassis = factory.SubFactory("tests.factories.hardware.WirelessChassisFactory")
    condition = Accessory.Condition.UNKNOWN
    serial_number = factory.Sequence(lambda number: f"accessory-serial-{number}")
