"""A chassis already known under another identity is handled the same by every ingest path."""

from collections.abc import Callable
from unittest.mock import patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.fake_vendor import BUILD_PLUGIN, FakeVendorPlugin

pytestmark = pytest.mark.django_db

KNOWN_IP = "192.0.2.10"
MOVED_IP = "192.0.2.20"
KNOWN_MAC = "00:11:22:33:44:55"


def _poll(manufacturer: Manufacturer, payloads: list[NormalizedChassis]) -> None:
    with patch(BUILD_PLUGIN, return_value=FakeVendorPlugin(payloads)):
        ManufacturerSyncService.sync_devices_for_manufacturer(manufacturer_code=manufacturer.code)


def _realtime(manufacturer: Manufacturer, payloads: list[NormalizedChassis]) -> None:
    plugin = FakeVendorPlugin(payloads)
    DeviceUpdateService.update_models_from_api_data(
        api_data=plugin.raw_devices,
        manufacturer=manufacturer,
        plugin=plugin,
    )


IngestPath = Callable[[Manufacturer, list[NormalizedChassis]], None]
PATHS: list[IngestPath] = [_poll, _realtime]


@pytest.fixture
def known() -> WirelessChassis:
    """One chassis the system already knows, with every identity key set."""
    return WirelessChassisFactory(
        manufacturer=ManufacturerFactory(code="ingest-vendor"),
        api_device_id="known-id",
        serial_number="serial-known",
        mac_address=KNOWN_MAC,
        ip=KNOWN_IP,
        status="online",
    )


@pytest.mark.parametrize("path", PATHS, ids=["poll", "realtime"])
@pytest.mark.parametrize(
    "identity",
    [
        {"serial_number": "serial-known"},
        {"mac_address": KNOWN_MAC},
    ],
    ids=["serial", "mac"],
)
def test_known_hardware_identity_under_a_new_api_id_and_address_is_the_same_chassis(
    path: IngestPath,
    identity: dict[str, str],
    known: WirelessChassis,
) -> None:
    """A serial or MAC match moves the existing chassis instead of adding a second one."""
    path(known.manufacturer, [NormalizedChassis(api_device_id="new-id", ip=MOVED_IP, **identity)])

    assert WirelessChassis.objects.count() == 1
    known.refresh_from_db()
    assert known.ip == MOVED_IP


@pytest.mark.parametrize("path", PATHS, ids=["poll", "realtime"])
def test_known_address_under_a_new_api_id_is_the_same_chassis(
    path: IngestPath,
    known: WirelessChassis,
) -> None:
    """An address match without a conflicting serial or MAC is the existing chassis."""
    path(known.manufacturer, [NormalizedChassis(api_device_id="new-id", ip=KNOWN_IP)])

    assert WirelessChassis.objects.count() == 1
    known.refresh_from_db()
    assert known.api_device_id == "known-id"


@pytest.mark.parametrize("path", PATHS, ids=["poll", "realtime"])
def test_known_api_id_at_a_new_address_moves_the_chassis(
    path: IngestPath,
    known: WirelessChassis,
) -> None:
    """The vendor's own id at a new address is a move, never a duplicate."""
    path(known.manufacturer, [NormalizedChassis(api_device_id="known-id", ip=MOVED_IP)])

    assert WirelessChassis.objects.count() == 1
    known.refresh_from_db()
    assert known.ip == MOVED_IP


@pytest.mark.parametrize("path", PATHS, ids=["poll", "realtime"])
@pytest.mark.parametrize(
    "identity",
    [{"serial_number": "serial-known"}, {"mac_address": KNOWN_MAC}],
    ids=["serial", "mac"],
)
def test_hardware_identity_owned_by_another_manufacturer_is_rejected(
    path: IngestPath,
    identity: dict[str, str],
    known: WirelessChassis,
) -> None:
    """One manufacturer cannot claim hardware already owned by another."""
    intruder = ManufacturerFactory(code="intruder-vendor")

    path(intruder, [NormalizedChassis(api_device_id="intruder-id", ip=MOVED_IP, **identity)])

    assert WirelessChassis.objects.filter(manufacturer=intruder).count() == 0
    known.refresh_from_db()
    assert known.ip == KNOWN_IP
