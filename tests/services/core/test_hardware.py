"""Behavior tests for hardware normalization and persistence hooks."""

from __future__ import annotations

from unittest.mock import Mock, call, patch

import pytest

from micboard.services.core.hardware import NormalizedHardware
from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from micboard.services.core.hardware_sync import HardwareSyncService
from tests.factories.hardware import WirelessChassisFactory


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


def test_normalization_canonicalizes_mac_identity_only() -> None:
    """Vendor case and delimiter choices do not change hardware identity."""
    normalized = NormalizedHardware.from_api(
        {
            "id": "receiver-2",
            "ip": "192.0.2.12",
            "macAddress": "AABBCCDDEEFF",
            "name": "AA-BB is a name, not a MAC",
        }
    )

    assert normalized is not None
    assert normalized.mac_address == "aa:bb:cc:dd:ee:ff"
    assert normalized.name == "AA-BB is a name, not a MAC"


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


def test_chassis_save_hook_threads_database_alias_to_channel_sync() -> None:
    """Provision channels on the same database used for the chassis write."""
    chassis = WirelessChassisFactory.build(id=17)

    with (
        patch.object(HardwareSyncService, "ensure_channel_count", return_value=(0, 0)) as ensure,
    ):
        HardwarePostSaveHooks.handle_chassis_save(
            chassis=chassis,
            created=False,
            using="inventory",
        )

    ensure.assert_called_once_with(chassis=chassis, using="inventory")


def test_chassis_lifecycle_logs_redact_vendor_hardware_identity() -> None:
    """Save/delete hooks retain numeric context without names, addresses, or vendor IDs."""
    private_identity = "private-chassis-identity"
    chassis = WirelessChassisFactory.build(
        id=17,
        name=private_identity,
        api_device_id=private_identity,
        ip="192.0.2.199",
    )
    with (
        patch.object(HardwareSyncService, "ensure_channel_count", return_value=(1, 1)),
        patch.object(HardwarePostSaveHooks, "handle_chassis_bulk_delete") as bulk_delete,
        patch("micboard.services.core.hardware_post_save_hooks.logger") as logger,
    ):
        HardwarePostSaveHooks.handle_chassis_save(chassis=chassis, created=True)
        HardwarePostSaveHooks.handle_chassis_delete(chassis=chassis)

    bulk_delete.assert_called_once_with(chassis_list=[chassis], using="default")
    rendered_calls = str(logger.method_calls)
    assert private_identity not in rendered_calls
    assert str(chassis.ip) not in rendered_calls


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
