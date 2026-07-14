"""Behavior tests for the public core hardware facade."""

from __future__ import annotations

import pytest

from micboard.services.core.hardware import HardwareService, NormalizedHardware
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory


@pytest.mark.parametrize(
    "payload",
    [
        {"ip": "192.0.2.10"},
        {"id": "device-1"},
        {"id": "   ", "ip": "192.0.2.10"},
    ],
)
def test_normalization_rejects_payloads_without_an_identity_and_address(
    payload: dict[str, str],
) -> None:
    """Require both stable API identity and an IP before persistence."""
    assert NormalizedHardware.from_api(payload) is None


def test_normalization_accepts_vendor_aliases_and_trims_values() -> None:
    """Normalize heterogeneous vendor keys into one hardware contract."""
    normalized = NormalizedHardware.from_api(
        {
            "api_device_id": " receiver-7 ",
            "ipAddress": " 192.0.2.7 ",
            "serialNumber": " serial-7 ",
            "macAddress": " 00:11:22:33:44:55 ",
            "model": " RX-7 ",
            "firmwareVersion": " 1.2.3 ",
            "networkMode": " dhcp ",
            "interfaceId": " eth0 ",
            "subnetMask": "255.255.255.0",
            "gateway": "192.0.2.1",
        }
    )

    assert normalized is not None
    assert normalized.api_device_id == "receiver-7"
    assert normalized.ip == "192.0.2.7"
    assert normalized.serial_number == "serial-7"
    assert normalized.mac_address == "00:11:22:33:44:55"
    assert normalized.name == "RX-7"
    assert normalized.model == "RX-7"
    assert normalized.firmware_version == "1.2.3"
    assert normalized.network_mode == "dhcp"
    assert normalized.interface_id == "eth0"
    assert normalized.subnet_mask == "255.255.255.0"
    assert normalized.gateway == "192.0.2.1"


def test_normalization_prefers_canonical_keys_and_supplies_safe_defaults() -> None:
    """Prefer canonical values when aliases coexist and default optional data."""
    normalized = NormalizedHardware.from_api(
        {
            "id": "canonical-id",
            "api_device_id": "alias-id",
            "ip": "2001:db8::10",
            "ip_address": "2001:db8::11",
            "name": "Rack A",
        }
    )

    assert normalized is not None
    assert normalized.api_device_id == "canonical-id"
    assert normalized.ip == "2001:db8::10"
    assert normalized.name == "Rack A"
    assert normalized.model == ""
    assert normalized.device_type == ""
    assert normalized.network_mode == "auto"
    assert normalized.subnet_mask is None


@pytest.mark.django_db
def test_facade_delegates_queries_and_writes_to_domain_services() -> None:
    """Keep the public facade useful while implementations remain decomposed."""
    chassis = WirelessChassisFactory(name="Spotlight Rack", status="online")
    unit = WirelessUnitFactory(
        base_chassis=chassis,
        manufacturer=chassis.manufacturer,
        name="Spotlight Pack",
        status="online",
    )

    assert HardwareService.get_chassis_by_ip(ip=chassis.ip) == chassis
    assert HardwareService.count_online_hardware() == {"chassis": 1, "units": 1}
    assert set(HardwareService.search_hardware(query="Spotlight")) == {chassis, unit}

    HardwareService.sync_unit_battery(unit=unit, battery_level=128)
    unit.refresh_from_db()
    assert unit.battery == 128
