"""Focused coverage for polling and realtime device persistence boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from micboard.integrations.sennheiser.normalizer import SENNHEISER_NORMALIZER
from micboard.integrations.shure.normalizer import SHURE_NORMALIZER
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis, NormalizedUnit
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.sync.device_update_service import DeviceUpdateService
from tests.factories.discovery import ManufacturerFactory


def test_realtime_update_does_not_reconcile_missing_chassis() -> None:
    """One realtime event cannot mark sibling chassis offline."""
    manufacturer = MagicMock()
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(api_device_id="device-1")
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
    plugin.normalize_device.return_value = NormalizedChassis(api_device_id="device-2")
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


def test_normalization_failure_redacts_raw_device_identifier_and_exception() -> None:
    """A normalization failure cannot disclose raw payload identifiers or exception details."""
    plugin = MagicMock()
    secret = "malformed-payload-secret"
    plugin.normalize_device.side_effect = ValueError(secret)

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
    ("normalizer", "device_id"),
    [
        (SHURE_NORMALIZER, "shure-device"),
        (SENNHEISER_NORMALIZER, "sennheiser-device"),
    ],
)
def test_shipped_normalizers_create_online_chassis(normalizer, device_id: str) -> None:
    """Built-in normalized payloads persist responding devices as online."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.side_effect = normalizer.normalize_device
    plugin.get_device_channels.return_value = []
    plugin.normalize_channels.return_value = []

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
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id=chassis.api_device_id,
        ip=str(chassis.ip),
    )
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
    plugin.normalize_device.side_effect = [
        NormalizedChassis(api_device_id="device-1"),
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


def test_unnormalizable_payloads_are_contained() -> None:
    """A payload the integration cannot normalize never reaches chassis persistence."""
    plugin = MagicMock()
    plugin.normalize_device.return_value = None

    assert (
        DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "empty"}],
            manufacturer=MagicMock(code="vendor"),
            plugin=plugin,
        )
        == 0
    )


@pytest.mark.django_db
def test_embedded_channels_persist_unit_telemetry_without_a_second_fetch() -> None:
    """Embedded channels are persisted as normalized, and unreported readings use defaults."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="embedded-device",
        ip="192.0.2.91",
        channels=[
            NormalizedChannel(number=1, unit=NormalizedUnit(slot=4)),
            NormalizedChannel(number=2, unit=None),
        ],
    )

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ) as alerts:
        updated = DeviceUpdateService.update_models_from_api_data(
            api_data=[{"id": "embedded-device"}],
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
    plugin.normalize_channels.assert_not_called()
    alerts.assert_called_once_with(unit)


@pytest.mark.django_db
def test_device_without_embedded_channels_uses_the_channel_endpoint() -> None:
    """Snapshots without embedded channels retain the established detail endpoint."""
    manufacturer = ManufacturerFactory()
    plugin = MagicMock()
    plugin.normalize_device.return_value = NormalizedChassis(
        api_device_id="detail-device",
        ip="192.0.2.92",
    )
    raw_channels = [{"channel": 2}, {"channel": 3, "tx": {"deviceName": "Detail transmitter"}}]
    plugin.get_device_channels.return_value = raw_channels
    plugin.normalize_channels.side_effect = SHURE_NORMALIZER.normalize_channels

    with patch(
        "micboard.services.sync.device_update_service.alert_manager.check_wireless_unit_alerts"
    ):
        assert (
            DeviceUpdateService.update_models_from_api_data(
                api_data=[{"id": "detail-device"}],
                manufacturer=manufacturer,
                plugin=plugin,
            )
            == 1
        )

    unit = WirelessUnit.objects.get(base_chassis__api_device_id="detail-device")
    assert unit.assigned_resource.channel_number == 3
    assert unit.name == "Detail transmitter"
    plugin.get_device_channels.assert_called_once_with("detail-device")
    plugin.normalize_channels.assert_called_once_with(raw_channels)


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
            api_slot=None,
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
