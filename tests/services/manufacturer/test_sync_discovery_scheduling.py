"""Discovery scheduling contracts for manufacturer inventory persistence."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from micboard.services.core.hardware import NormalizedHardware
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.discovery_trigger_service import (
    coalesce_discovery_scheduling,
    schedule_discovery_on_commit,
)
from tests.factories.discovery import ManufacturerFactory


def _payload(number: int) -> NormalizedHardware:
    """Build one unique bounded inventory payload."""
    return NormalizedHardware(
        api_device_id=f"device-{number}",
        ip=f"198.51.100.{number + 1}",
        serial_number=f"serial-{number}",
        mac_address=f"02:00:00:00:00:{number:02x}",
        name=f"Receiver {number}",
        model="RX-1",
        device_type="receiver",
        firmware_version="",
        hosted_firmware_version="",
        description="",
        subnet_mask=None,
        gateway=None,
        network_mode="auto",
        interface_id="",
    )


@pytest.mark.django_db
def test_hundred_device_sync_registers_one_discovery_dispatch(
    django_capture_on_commit_callbacks,
) -> None:
    """Autocommit-style row saves collapse into one post-batch reconciliation."""
    manufacturer = ManufacturerFactory(code="batch-vendor")
    payloads = [_payload(number) for number in range(100)]
    plugin = Mock()
    plugin.get_devices.return_value = [{"id": payload.api_device_id} for payload in payloads]

    with (
        patch(
            "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
            return_value=plugin,
        ),
        patch.object(
            ManufacturerSyncService,
            "_normalize_devices",
            return_value=payloads,
        ),
        patch(
            "micboard.services.core.hardware_post_save_hooks."
            "HardwarePostSaveHooks._ensure_channel_count"
        ),
        patch(
            "micboard.services.sync.discovery_trigger_service._dispatch_scheduled_discovery"
        ) as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = ManufacturerSyncService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer.code,
        )

    assert result["success"] is True
    assert result["devices_added"] == 100
    dispatch.assert_called_once_with(
        manufacturer_id=manufacturer.pk,
        scan_cidrs=False,
        scan_fqdns=False,
    )


@pytest.mark.django_db(transaction=True)
def test_nested_batch_coalescing_keeps_one_unique_schedule() -> None:
    """Nested service orchestration shares its outer pending-request set."""
    with (
        patch(
            "micboard.services.sync.discovery_trigger_service._dispatch_scheduled_discovery"
        ) as dispatch,
        coalesce_discovery_scheduling(),
    ):
        schedule_discovery_on_commit(
            manufacturer_id=71,
            scan_cidrs=False,
            scan_fqdns=False,
            using="default",
        )
        with coalesce_discovery_scheduling():
            schedule_discovery_on_commit(
                manufacturer_id=71,
                scan_cidrs=False,
                scan_fqdns=False,
                using="default",
            )

    dispatch.assert_called_once_with(
        manufacturer_id=71,
        scan_cidrs=False,
        scan_fqdns=False,
    )
