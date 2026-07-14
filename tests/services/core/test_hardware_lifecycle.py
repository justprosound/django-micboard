"""Service tests for hardware lifecycle state transitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

import pytest

from micboard.models.audit.activity_log import ActivityLog
from micboard.services.core.hardware_lifecycle import (
    HardwareLifecycleManager,
    HardwareStatus,
    get_lifecycle_manager,
    map_api_state_to_status,
)
from micboard.services.maintenance.logging import StructuredLogger
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory


def test_status_helpers_expose_stable_choices_and_activity_groups() -> None:
    """Publish Django choices and exhaustive active/inactive groupings."""
    assert ("discovered", "Discovered") in HardwareStatus.choices()
    assert HardwareStatus.active_states() == ["online", "degraded", "provisioning"]
    assert HardwareStatus.inactive_states() == ["offline", "maintenance", "retired"]


@pytest.mark.django_db
def test_valid_transition_persists_and_emits_structured_context() -> None:
    """Persist an allowed transition under a row lock and log old/new state."""
    unit = WirelessUnitFactory(status="discovered", last_seen=None)
    structured_logger = Mock()
    manager = HardwareLifecycleManager(structured_logger=structured_logger)
    before = timezone.now()

    transitioned = manager.transition_device(
        unit,
        HardwareStatus.PROVISIONING,
        reason="Approved for provisioning",
        metadata={"ticket": "RF-7"},
    )

    assert transitioned is True
    unit.refresh_from_db()
    assert unit.status == "provisioning"
    assert unit.last_seen is not None
    assert unit.last_seen >= before
    logged_device = structured_logger.log_crud_update.call_args.args[0]
    assert logged_device.pk == unit.pk
    assert structured_logger.log_crud_update.call_args.kwargs["old_values"]["status"] == (
        "discovered"
    )
    assert structured_logger.log_crud_update.call_args.kwargs["new_values"]["status"] == (
        "provisioning"
    )


@pytest.mark.django_db
def test_default_lifecycle_audit_uses_maintenance_structured_logger() -> None:
    """A manager without injected test doubles must execute the real audit seam."""
    unit = WirelessUnitFactory(status="discovered", last_seen=None)

    with patch.object(StructuredLogger, "log_crud_update") as log_update:
        manager = HardwareLifecycleManager()
        assert manager.transition_device(unit, HardwareStatus.PROVISIONING) is True

    logged_device = log_update.call_args.args[0]
    assert logged_device.pk == unit.pk
    assert log_update.call_args.kwargs["old_values"]["status"] == "discovered"
    assert log_update.call_args.kwargs["new_values"]["status"] == "provisioning"
    assert log_update.call_args.kwargs["using"] == "default"


def test_lifecycle_audit_threads_the_instance_database_alias() -> None:
    """Carry a non-default device alias through the complete structured audit seam."""
    unit = WirelessUnitFactory.build(id=17, status="discovered", last_seen=None)
    unit._state.db = "inventory"
    alias_queryset = Mock()
    alias_queryset.select_for_update.return_value.get.return_value = unit
    audit_log = Mock()

    with (
        patch.object(type(unit)._default_manager, "using", return_value=alias_queryset) as using,
        patch("micboard.services.core.hardware_lifecycle.transaction.atomic") as atomic,
        patch.object(unit, "save"),
        patch.object(ActivityLog, "log_crud", return_value=audit_log) as log_crud,
    ):
        manager = HardwareLifecycleManager(structured_logger=StructuredLogger())
        assert manager.transition_device(unit, HardwareStatus.PROVISIONING) is True

    atomic.assert_called_once_with(using="inventory")
    using.assert_called_once_with("inventory")
    assert log_crud.call_args.kwargs["using"] == "inventory"


def test_crud_audit_binds_content_type_lookup_and_write_to_database_alias() -> None:
    """Persist both halves of a generic audit relation on one connection."""
    unit = WirelessUnitFactory.build(id=17)
    content_type = ContentType(app_label="micboard", model="wirelessunit")
    content_types = Mock()
    content_types.get_for_model.return_value = content_type

    with (
        patch.object(ContentType.objects, "db_manager", return_value=content_types) as db_manager,
        patch.object(ActivityLog, "save") as save,
    ):
        audit_log = ActivityLog.log_crud(
            operation=ActivityLog.UPDATE,
            obj=unit,
            old_values={"status": "discovered"},
            new_values={"status": "provisioning"},
            using="inventory",
        )

    db_manager.assert_called_once_with("inventory")
    content_types.get_for_model.assert_called_once_with(unit)
    save.assert_called_once_with(using="inventory")
    assert audit_log.content_type is content_type


def test_crud_audit_normalizes_django_native_values_for_json_storage() -> None:
    """Lifecycle timestamps must not make otherwise valid audit writes fail."""
    unit = WirelessUnitFactory.build(id=17)
    changed_at = datetime(2026, 7, 13, 12, 30, tzinfo=UTC)
    content_type = ContentType(app_label="micboard", model="wirelessunit")
    content_types = Mock()
    content_types.get_for_model.return_value = content_type

    with (
        patch.object(ContentType.objects, "db_manager", return_value=content_types),
        patch.object(ActivityLog, "save"),
    ):
        audit_log = ActivityLog.log_crud(
            operation=ActivityLog.UPDATE,
            obj=unit,
            old_values={"last_seen": None},
            new_values={"last_seen": changed_at},
        )

    assert audit_log.new_values == {"last_seen": "2026-07-13T12:30:00Z"}


@pytest.mark.django_db
def test_valid_chassis_transition_uses_only_fields_present_on_chassis() -> None:
    """Transition chassis even though it has no WirelessUnit updated_at field."""
    chassis = WirelessChassisFactory(status="discovered")
    manager = HardwareLifecycleManager(structured_logger=Mock())

    assert manager.transition_device(chassis, HardwareStatus.PROVISIONING) is True
    chassis.refresh_from_db()
    assert chassis.status == "provisioning"
    assert chassis.last_seen is not None


@pytest.mark.django_db
def test_invalid_transition_does_not_mutate_device() -> None:
    """Reject transitions out of the terminal retired state."""
    unit = WirelessUnitFactory(status="retired", last_seen=None)
    structured_logger = Mock()
    manager = HardwareLifecycleManager(structured_logger=structured_logger)

    assert manager.transition_device(unit, HardwareStatus.ONLINE) is False
    unit.refresh_from_db()
    assert unit.status == "retired"
    assert unit.last_seen is None
    structured_logger.log_crud_update.assert_not_called()


@pytest.mark.django_db
def test_transition_validates_locked_state_instead_of_stale_caller_state() -> None:
    """A stale instance cannot resurrect a device after a terminal transition."""
    stale_unit = WirelessUnitFactory(status="online", last_seen=None)
    type(stale_unit).objects.filter(pk=stale_unit.pk).update(status="retired")
    manager = HardwareLifecycleManager(structured_logger=Mock())

    assert manager.transition_device(stale_unit, HardwareStatus.OFFLINE) is False
    stale_unit.refresh_from_db()
    assert stale_unit.status == "retired"
    assert stale_unit.last_seen is None


@pytest.mark.django_db
def test_maintenance_transition_syncs_status_when_service_is_configured() -> None:
    """Push administrative maintenance transitions through the API seam."""
    unit = WirelessUnitFactory(status="online")
    manager = HardwareLifecycleManager(service_code="vendor", structured_logger=Mock())

    with patch("micboard.services.core.device_api_status_sync.sync_status_to_api") as sync_status:
        assert manager.mark_maintenance(unit, reason="Planned work") is True

    unit.refresh_from_db()
    assert unit.status == "maintenance"
    synced_device = sync_status.call_args.args[1]
    assert synced_device.pk == unit.pk
    assert sync_status.call_args.args[0] == "vendor"
    assert sync_status.call_args.args[2:] == ("maintenance", None)


@pytest.mark.parametrize(
    ("method_name", "kwargs", "target_status", "expected_kwargs"),
    [
        (
            "mark_discovered",
            {"device_data": {"source": "scan"}},
            "discovered",
            {
                "reason": "Device discovered via API",
                "metadata": {"source": "scan"},
            },
        ),
        (
            "mark_online",
            {"health_data": {"rssi": -55}},
            "online",
            {
                "reason": "Device responding to polls",
                "metadata": {"rssi": -55},
            },
        ),
        (
            "mark_degraded",
            {"warnings": ["battery"]},
            "degraded",
            {
                "reason": "Device has warnings or performance issues",
                "metadata": {"warnings": ["battery"]},
            },
        ),
        (
            "mark_offline",
            {"reason": "No heartbeat"},
            "offline",
            {"reason": "No heartbeat"},
        ),
        (
            "mark_retired",
            {"reason": "Replaced"},
            "retired",
            {"reason": "Replaced"},
        ),
    ],
)
def test_transition_helpers_delegate_context_without_reimplementing_state_logic(
    method_name: str,
    kwargs: dict[str, object],
    target_status: str,
    expected_kwargs: dict[str, object],
) -> None:
    """Keep convenience methods as thin, explicit transition adapters."""
    device = WirelessUnitFactory.build()
    manager = HardwareLifecycleManager(structured_logger=Mock())

    with patch.object(manager, "transition_device", return_value=True) as transition:
        assert getattr(manager, method_name)(device, **kwargs) is True

    transition.assert_called_once_with(device, target_status, **expected_kwargs)


@pytest.mark.django_db
def test_update_stale_devices_excludes_protected_and_fresh_chassis() -> None:
    """Only attempt to offline stale, non-protected chassis."""
    stale_at = timezone.now() - timedelta(minutes=15)
    stale = WirelessChassisFactory(status="online", last_seen=stale_at)
    WirelessChassisFactory(status="maintenance", last_seen=stale_at)
    WirelessChassisFactory(status="retired", last_seen=stale_at)
    WirelessChassisFactory(status="online", last_seen=timezone.now())
    manager = HardwareLifecycleManager(structured_logger=Mock())

    with patch.object(manager, "mark_offline", return_value=True) as mark_offline:
        assert manager.update_stale_devices(timeout_minutes=5) == 1

    marked_device = mark_offline.call_args.args[0]
    assert marked_device.pk == stale.pk
    assert mark_offline.call_args.kwargs == {"reason": "Stale heartbeat"}


@pytest.mark.django_db
def test_create_with_state_normalizes_required_identity_and_api_status() -> None:
    """Create discovered inventory from supported vendor identity aliases."""
    manufacturer = ManufacturerFactory()
    manager = HardwareLifecycleManager(structured_logger=Mock())

    chassis = manager.create_with_state(
        manufacturer,
        {
            "id": "api-rx-10",
            "ipAddress": "192.0.2.10",
            "model": "RX-10",
            "serialNumber": "serial-10",
            "deviceState": "online",
        },
    )

    assert chassis is not None
    assert chassis.manufacturer == manufacturer
    assert chassis.api_device_id == "api-rx-10"
    assert chassis.ip == "192.0.2.10"
    assert chassis.status == "online"
    assert chassis.last_seen is not None


@pytest.mark.parametrize(
    "api_data",
    [
        {"id": "api-rx-10"},
        {"ip": "192.0.2.10"},
    ],
)
@pytest.mark.django_db
def test_create_with_state_rejects_incomplete_identity(api_data: dict[str, str]) -> None:
    """Do not create hardware when the API omits identity or address."""
    manager = HardwareLifecycleManager(structured_logger=Mock())

    assert manager.create_with_state(ManufacturerFactory(), api_data) is None


def test_poll_handlers_delegate_mapped_state_and_handle_missing_state() -> None:
    """Translate poll states while rejecting payloads without a state."""
    device = WirelessUnitFactory.build(status="discovered")
    manager = HardwareLifecycleManager(structured_logger=Mock())

    assert manager.handle_poll_result(device, {"battery": 80}) is False
    with patch.object(manager, "transition_device", return_value=True) as transition:
        assert manager.handle_poll_result(device, {"deviceState": "online"}) is True
        assert manager.handle_missing_device(device) is True

    assert transition.call_args_list[0].args == (device, "online")
    assert transition.call_args_list[0].kwargs == {"metadata": {"source": "poll"}}
    assert transition.call_args_list[1].args == (device, "offline")
    assert transition.call_args_list[1].kwargs == {"reason": "Missing in poll"}


@pytest.mark.parametrize(
    ("api_state", "current_status", "expected"),
    [
        ("ONLINE", "discovered", "online"),
        ("DISCOVERING", "offline", "provisioning"),
        ("OFFLINE", "online", "offline"),
        ("UNKNOWN", "online", "discovered"),
        ("VENDOR_PRIVATE", "degraded", "degraded"),
    ],
)
def test_api_state_mapping_preserves_current_state_for_unknown_vendor_values(
    api_state: str,
    current_status: str,
    expected: str,
) -> None:
    """Map documented states without inventing semantics for vendor extensions."""
    assert map_api_state_to_status(api_state, current_status) == expected


def test_manager_factory_and_history_placeholder_have_explicit_contracts() -> None:
    """Expose contextual manager construction and a stable empty history result."""
    manager = get_lifecycle_manager("vendor")
    device = WirelessUnitFactory.build()

    assert isinstance(manager, HardwareLifecycleManager)
    assert manager.service_code == "vendor"
    assert manager.get_state_history(device) is None
