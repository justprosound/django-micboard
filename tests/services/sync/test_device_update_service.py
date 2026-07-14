"""Focused coverage for polling and realtime device persistence boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from micboard.integrations.sennheiser.transformers import SennheiserDataTransformer
from micboard.integrations.shure.transformers import ShureDataTransformer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
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
            WirelessChassisPersistenceService,
            "upsert",
            return_value=(SimpleNamespace(pk=11), True),
        ),
        patch.object(DeviceUpdateService, "_reconcile_chassis_lifecycle"),
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
            WirelessChassisPersistenceService,
            "upsert",
            return_value=(SimpleNamespace(pk=22), True),
        ),
        patch.object(DeviceUpdateService, "_reconcile_chassis_lifecycle"),
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


def test_transform_failure_redacts_raw_device_identifier_and_exception() -> None:
    """A transform failure cannot disclose raw payload identifiers or exception details."""
    plugin = MagicMock()
    secret = "malformed-payload-secret"
    plugin.transform_device_data.side_effect = ValueError(secret)

    with patch("micboard.services.sync.device_update_service.logger") as logger:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "raw-device-3"}],
            manufacturer=MagicMock(),
            plugin=plugin,
        )

    assert updated == 0
    assert logger.exception.call_args.args == (
        "Error updating vendor device at snapshot position %s",
        1,
    )
    assert "raw-device-3" not in str(logger.exception.call_args)
    assert secret not in str(logger.exception.call_args.kwargs["exc_info"][1])


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
            WirelessChassisPersistenceService,
            "upsert",
            return_value=(SimpleNamespace(pk=11), True),
        ),
        patch.object(DeviceUpdateService, "_reconcile_chassis_lifecycle"),
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


def test_empty_and_identifierless_transforms_are_contained() -> None:
    """Invalid normalized records cannot escape into chassis persistence."""
    plugin = MagicMock()
    plugin.transform_device_data.side_effect = [None, {"api_device_id": "  "}]

    assert (
        DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "empty"}, {"api_device_id": "missing-id"}],
            manufacturer=MagicMock(code="vendor"),
            plugin=plugin,
        )
        == 0
    )


@pytest.mark.django_db
def test_embedded_normalized_channels_persist_null_safe_telemetry() -> None:
    """Embedded snapshots are not transformed twice and nullable strings stay valid."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.transform_device_data.return_value = {
        "api_device_id": "embedded-device",
        "ip": "192.0.2.91",
        "channels": [
            {
                "channel": 1,
                "tx": {
                    "slot": 4,
                    "battery": None,
                    "battery_type": None,
                    "runtime": None,
                    "battery_health": None,
                    "audio_level": None,
                    "rf_level": None,
                    "frequency": None,
                    "antenna": None,
                    "tx_offset": None,
                    "quality": None,
                    "status": None,
                    "name": None,
                },
            }
        ],
    }

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ) as alerts:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "embedded-device", "channels": [{}]}],
            manufacturer=manufacturer,
            plugin=plugin,
        )

    unit = WirelessUnit.objects.get(base_chassis__api_device_id="embedded-device")
    assert updated == 1
    assert unit.slot == 4
    assert unit.battery == 255
    assert unit.battery_type == ""
    assert unit.battery_runtime == ""
    assert unit.audio_level == 0
    assert unit.rf_level == 0
    assert unit.tx_offset == 255
    assert unit.quality == 255
    plugin.get_device_channels.assert_not_called()
    plugin.transform_transmitter_data.assert_not_called()
    alerts.assert_called_once_with(unit)


@pytest.mark.django_db
def test_separate_channel_endpoint_uses_vendor_transmitter_transform() -> None:
    """Snapshots without embedded channels retain the established detail endpoint."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.transform_device_data.return_value = {
        "api_device_id": "detail-device",
        "ip": "192.0.2.92",
        "channels": [],
    }
    plugin.get_device_channels.return_value = [
        {"channel": 2},
        {"channel": 3, "tx": {"raw": True}},
    ]
    plugin.transform_transmitter_data.return_value = {
        "battery": 100,
        "name": "Detail transmitter",
    }

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ):
        assert (
            DeviceUpdateService.update_models_from_api_data(
                api_data=[{"id": "detail-device", "channels": []}],
                manufacturer=manufacturer,
                plugin=plugin,
            )
            == 1
        )

    unit = WirelessUnit.objects.get(base_chassis__api_device_id="detail-device")
    assert unit.assigned_resource.channel_number == 3
    assert unit.name == "Detail transmitter"
    plugin.get_device_channels.assert_called_once_with("detail-device")
    plugin.transform_transmitter_data.assert_called_once_with({"raw": True}, 3)


@pytest.mark.parametrize(
    ("status", "transition_result", "mark_online_result", "message"),
    [
        ("discovered", False, True, "Could not provision"),
        ("offline", True, False, "Could not mark"),
    ],
)
def test_existing_chassis_lifecycle_failures_abort_updates(
    status: str,
    transition_result: bool,
    mark_online_result: bool,
    message: str,
) -> None:
    """Polling never bypasses a rejected chassis lifecycle transition."""
    chassis = MagicMock(status=status, pk=17)
    lifecycle = MagicMock()
    lifecycle.transition_device.return_value = transition_result
    lifecycle.mark_online.return_value = mark_online_result
    with (
        patch(
            "micboard.services.core.hardware_lifecycle.HardwareLifecycleManager",
            return_value=lifecycle,
        ),
        pytest.raises(RuntimeError, match=message),
    ):
        DeviceUpdateService._reconcile_chassis_lifecycle(
            chassis=chassis,
            created=False,
            manufacturer=MagicMock(code="vendor"),
        )


def test_chassis_persistence_logs_only_database_identifiers() -> None:
    """Realtime persistence logs cannot expose vendor names or device identifiers."""
    private_identity = "private-vendor-device-identity"
    chassis = MagicMock(status="online", pk=17)
    manufacturer = SimpleNamespace(code=private_identity, pk=9)
    with (
        patch("micboard.services.core.hardware_lifecycle.HardwareLifecycleManager"),
        patch("micboard.services.sync.device_update_service.logger") as logger,
    ):
        DeviceUpdateService._reconcile_chassis_lifecycle(
            chassis=chassis,
            created=True,
            manufacturer=manufacturer,
        )

    assert logger.info.call_args.args == (
        "Created wireless chassis %s for manufacturer %s",
        chassis.pk,
        manufacturer.pk,
    )
    assert private_identity not in str(logger.method_calls)


def test_derived_unit_slot_resolves_collisions_deterministically() -> None:
    """Generated slots advance until they no longer collide with existing units."""
    channel = MagicMock()
    assigned = MagicMock()
    assigned.only.return_value.first.return_value = None
    occupied = MagicMock()
    occupied.exists.side_effect = [True, False]
    with patch.object(WirelessUnit.objects, "filter", side_effect=[assigned, occupied, occupied]):
        slot = DeviceUpdateService._assign_unit_slot(
            channel=channel,
            transformed_unit={},
            api_device_id="stable-device",
            channel_number=7,
        )

    assert 0 <= slot < 10000
    assert occupied.exists.call_count == 2


def test_offline_reconciliation_continues_after_one_lifecycle_failure() -> None:
    """One bad chassis cannot stop sibling offline alerts from being evaluated."""
    first = SimpleNamespace(pk=1)
    second = SimpleNamespace(pk=2)
    offline_queryset = MagicMock()
    offline_queryset.exists.return_value = True
    offline_queryset.__iter__.return_value = iter([first, second])
    initial_queryset = MagicMock()
    initial_queryset.exclude.return_value = offline_queryset
    unit = object()
    refreshed = SimpleNamespace(field_units=MagicMock())
    refreshed.field_units.all.return_value = [unit]
    refreshed_queryset = MagicMock()
    refreshed_queryset.prefetch_related.return_value = [refreshed]
    lifecycle = MagicMock()
    lifecycle.mark_offline.side_effect = [None, RuntimeError("transition failed")]
    manufacturer = MagicMock(code="vendor", name="Vendor")

    with (
        patch.object(
            WirelessChassis.objects,
            "filter",
            side_effect=[initial_queryset, refreshed_queryset],
        ),
        patch(
            "micboard.services.core.hardware_lifecycle.HardwareLifecycleManager",
            return_value=lifecycle,
        ),
        patch(
            "micboard.services.sync.device_update_service.alert_manager.check_hardware_offline_alerts"
        ) as alerts,
    ):
        DeviceUpdateService.mark_offline_receivers(
            manufacturer=manufacturer,
            active_chassis_ids=[99],
        )

    alerts.assert_called_once_with(unit)
