"""Behavior tests for the public core hardware facade."""

from __future__ import annotations

from unittest.mock import Mock, call, patch

from django.utils import timezone

import pytest

from micboard.services.core.hardware import HardwareService, NormalizedHardware
from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from micboard.services.core.hardware_query import HardwareQueryService
from micboard.services.core.hardware_sync import HardwareSyncService
from tests.async_utils import run_async_with_heartbeat
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


@pytest.mark.django_db(transaction=True)
def test_async_hardware_queries_materialize_results_before_returning() -> None:
    """Async query APIs never leak lazy ORM evaluation into the event loop."""
    online_chassis = WirelessChassisFactory(status="online", is_online=True)
    WirelessChassisFactory(status="offline", is_online=False)
    active_unit = WirelessUnitFactory(
        base_chassis=online_chassis,
        manufacturer=online_chassis.manufacturer,
        status="online",
        last_seen=timezone.now(),
        battery=10,
    )

    async def evaluate_results() -> tuple[list[int], list[int], list[int], list[int]]:
        active_chassis = await HardwareQueryService.aget_active_chassis()
        online = await HardwareQueryService.aget_online_chassis()
        active_units = await HardwareQueryService.aget_active_units()
        low_battery = await HardwareQueryService.aget_low_battery_units(threshold=20)

        assert isinstance(active_chassis, list)
        assert isinstance(online, list)
        assert isinstance(active_units, list)
        assert isinstance(low_battery, list)
        return (
            [chassis.pk for chassis in active_chassis],
            [chassis.pk for chassis in online],
            [unit.pk for unit in active_units],
            [unit.pk for unit in low_battery],
        )

    active_ids, online_ids, active_unit_ids, low_battery_ids = run_async_with_heartbeat(
        evaluate_results()
    )

    assert active_ids == [online_chassis.pk]
    assert online_ids == [online_chassis.pk]
    assert active_unit_ids == [active_unit.pk]
    assert low_battery_ids == [active_unit.pk]


def test_chassis_save_hook_threads_database_alias_to_channel_sync() -> None:
    """Provision channels on the same database used for the chassis write."""
    chassis = WirelessChassisFactory.build(id=17)

    with (
        patch.object(HardwareSyncService, "ensure_channel_count", return_value=(0, 0)) as ensure,
        patch("micboard.services.core.hardware_post_save_hooks.transaction.on_commit"),
    ):
        HardwarePostSaveHooks.handle_chassis_save(
            chassis=chassis,
            created=False,
            using="inventory",
        )

    ensure.assert_called_once_with(chassis=chassis, using="inventory")


def test_channel_sync_binds_all_reads_and_writes_to_database_alias() -> None:
    """Never leak RF channel reconciliation onto the default connection."""
    chassis = Mock(pk=17, role="receiver")
    chassis.get_expected_channel_count.return_value = 2
    alias_channels = Mock()
    existing_channels = Mock()
    existing_channels.values_list.return_value = [1, 3]
    excess_channel = Mock()
    alias_channels.filter.side_effect = [existing_channels, excess_channel]

    with patch(
        "micboard.models.rf_coordination.RFChannel.objects.using",
        return_value=alias_channels,
    ) as using:
        result = HardwareSyncService.ensure_channel_count(
            chassis=chassis,
            using="inventory",
        )

    assert result == (1, 1)
    using.assert_called_once_with("inventory")
    assert alias_channels.filter.call_args_list == [
        call(chassis_id=17),
        call(chassis_id=17, channel_number=3),
    ]
    alias_channels.create.assert_called_once_with(
        chassis_id=17,
        channel_number=2,
        link_direction="receive",
    )
    excess_channel.delete.assert_called_once_with()
