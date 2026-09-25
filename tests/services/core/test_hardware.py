"""Behavior tests for hardware persistence hooks."""

from __future__ import annotations

from unittest.mock import Mock, call, patch

import pytest

from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from micboard.services.core.hardware_sync import HardwareSyncService
from tests.factories.hardware import WirelessChassisFactory


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


@pytest.mark.parametrize(("online", "expected_status"), [(True, "online"), (False, "offline")])
def test_hardware_status_sync_persists_the_requested_state(
    online: bool,
    expected_status: str,
) -> None:
    """Persist the canonical lifecycle status without a forwarding async API."""
    chassis = Mock(status="discovered")

    HardwareSyncService.sync_hardware_status(obj=chassis, online=online)

    assert chassis.status == expected_status
    chassis.save.assert_called_once_with(update_fields=["status"])


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
        "micboard.models.rf_coordination.rf_channel.RFChannel.objects.using",
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


@pytest.mark.parametrize(
    ("role", "expected_direction"),
    [("transmitter", "send"), ("transceiver", "bidirectional")],
)
def test_channel_sync_derives_link_direction_from_chassis_role(
    role: str,
    expected_direction: str,
) -> None:
    """Create missing channels with the chassis role's RF direction."""
    chassis = Mock(pk=17, role=role)
    chassis.get_expected_channel_count.return_value = 1
    alias_channels = Mock()
    alias_channels.filter.return_value.values_list.return_value = []

    with patch(
        "micboard.models.rf_coordination.rf_channel.RFChannel.objects.using",
        return_value=alias_channels,
    ):
        assert HardwareSyncService.ensure_channel_count(chassis=chassis) == (1, 0)

    alias_channels.create.assert_called_once_with(
        chassis_id=17,
        channel_number=1,
        link_direction=expected_direction,
    )
