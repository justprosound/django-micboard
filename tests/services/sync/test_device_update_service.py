"""Focused coverage for polling and realtime device persistence boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from micboard.integrations.sennheiser.transformers import SennheiserDataTransformer
from micboard.integrations.shure.transformers import ShureDataTransformer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import ManufacturerFactory


def test_realtime_update_does_not_reconcile_missing_chassis() -> None:
    """One realtime event cannot mark sibling chassis offline."""
    manufacturer = MagicMock()
    plugin = MagicMock()
    plugin.transform_device_data.return_value = {"api_device_id": "device-1"}
    plugin.get_device_channels.return_value = []

    with (
        patch.object(
            DeviceUpdateService,
            "_update_chassis",
            return_value=SimpleNamespace(pk=11),
        ),
        patch.object(DeviceUpdateService, "mark_offline_receivers") as mark_offline,
    ):
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "device-1"}],
            manufacturer=manufacturer,
            plugin=plugin,
        )

    assert updated == 1
    mark_offline.assert_not_called()


def test_authoritative_snapshot_reconciles_only_missing_chassis() -> None:
    """Full snapshots pass their persisted chassis identifiers to reconciliation."""
    manufacturer = MagicMock()
    plugin = MagicMock()
    plugin.transform_device_data.return_value = {"api_device_id": "device-2"}
    plugin.get_device_channels.return_value = []

    with (
        patch.object(
            DeviceUpdateService,
            "_update_chassis",
            return_value=SimpleNamespace(pk=22),
        ),
        patch.object(DeviceUpdateService, "mark_offline_receivers") as mark_offline,
    ):
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "device-2"}],
            manufacturer=manufacturer,
            plugin=plugin,
            authoritative_snapshot=True,
        )

    assert updated == 1
    mark_offline.assert_called_once_with(
        manufacturer=manufacturer,
        active_chassis_ids=[22],
    )


def test_transform_failure_logs_raw_device_identifier() -> None:
    """A transform failure is contained before normalized identifiers exist."""
    plugin = MagicMock()
    plugin.transform_device_data.side_effect = ValueError("malformed payload")

    with patch("micboard.services.sync.device_update_service.logger") as logger:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "raw-device-3"}],
            manufacturer=MagicMock(),
            plugin=plugin,
        )

    assert updated == 0
    logger.exception.assert_called_once_with("Error updating device %s", "raw-device-3")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("transformer", "device_id"),
    [
        (ShureDataTransformer, "shure-device"),
        (SennheiserDataTransformer, "sennheiser-device"),
    ],
)
def test_shipped_transformers_create_online_chassis(transformer, device_id: str) -> None:
    """Built-in normalized payloads persist responding devices as online."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.transform_device_data.side_effect = transformer.transform_device_data
    plugin.get_device_channels.return_value = []

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": device_id, "ip": "192.0.2.81", "modelName": "Receiver"}],
        manufacturer=manufacturer,
        plugin=plugin,
    )

    chassis = WirelessChassis.objects.get(
        manufacturer=manufacturer,
        api_device_id=device_id,
    )
    assert updated == 1
    assert chassis.status == "online"
    assert chassis.is_online is True


@pytest.mark.django_db
def test_existing_discovered_chassis_reaches_online_through_valid_transitions() -> None:
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="existing-device",
        ip="192.0.2.82",
        status="discovered",
    )
    plugin = MagicMock()
    plugin.transform_device_data.return_value = {
        "api_device_id": chassis.api_device_id,
        "ip": str(chassis.ip),
    }
    plugin.get_device_channels.return_value = []

    updated = DeviceUpdateService.update_models_from_api_data(
        api_data=[{"id": chassis.api_device_id}],
        manufacturer=manufacturer,
        plugin=plugin,
    )

    chassis.refresh_from_db()
    assert updated == 1
    assert chassis.status == "online"
    assert chassis.is_online is True


def test_incomplete_authoritative_snapshot_never_marks_devices_offline() -> None:
    manufacturer = MagicMock(code="vendor")
    plugin = MagicMock()
    plugin.transform_device_data.side_effect = [
        {"api_device_id": "device-1"},
        ValueError("malformed payload"),
    ]
    plugin.get_device_channels.return_value = []

    with (
        patch.object(
            DeviceUpdateService,
            "_update_chassis",
            return_value=SimpleNamespace(pk=11),
        ),
        patch.object(DeviceUpdateService, "mark_offline_receivers") as mark_offline,
    ):
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "device-1"}, {"id": "device-2"}],
            manufacturer=manufacturer,
            plugin=plugin,
            authoritative_snapshot=True,
        )

    assert updated == 1
    mark_offline.assert_not_called()
