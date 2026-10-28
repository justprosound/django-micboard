"""Service tests for hardware lifecycle state transitions."""

import re
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.models.audit.activity_log import ActivityLog
from micboard.services.core.hardware_lifecycle import (
    DeviceKind,
    HardwareLifecycleManager,
    HardwareStatus,
    ensure_valid_transition,
    is_valid_transition,
    map_api_state_to_status,
)
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory


@pytest.mark.django_db
def test_valid_transition_persists_and_emits_one_audit_event() -> None:
    """Persist an allowed transition and emit exactly one lifecycle audit event."""
    unit = WirelessUnitFactory(status="discovered", last_seen=None)
    manager = HardwareLifecycleManager()
    before = timezone.now()
    audits_before = ActivityLog.objects.filter(object_id=unit.pk).count()

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
    audits = ActivityLog.objects.filter(object_id=unit.pk).order_by("pk")
    assert audits.count() == audits_before + 1
    audit = audits.last()
    assert audit is not None
    assert audit.activity_type == "wireless_unit"
    assert audit.operation == "status_change"
    assert audit.old_values == {"status": "discovered"}
    assert audit.new_values == {"status": "provisioning"}


@pytest.mark.django_db
def test_same_status_transition_does_not_emit_audit_event() -> None:
    """Refreshing last_seen without a state change must not create audit noise."""
    unit = WirelessUnitFactory(status="discovered", last_seen=None)
    audits_before = ActivityLog.objects.filter(object_id=unit.pk).count()

    assert HardwareLifecycleManager().transition_device(unit, HardwareStatus.DISCOVERED) is True

    assert ActivityLog.objects.filter(object_id=unit.pk).count() == audits_before


def test_lifecycle_audit_threads_the_instance_database_alias() -> None:
    """Carry a non-default device alias through the lifecycle save seam."""
    unit = WirelessUnitFactory.build(id=17, status="discovered", last_seen=None)
    unit._state.db = "inventory"
    alias_queryset = Mock()
    alias_queryset.select_for_update.return_value.get.return_value = unit
    with (
        patch.object(type(unit)._default_manager, "using", return_value=alias_queryset) as using,
        patch("micboard.services.core.hardware_lifecycle.transaction.atomic") as atomic,
        patch.object(unit, "save") as save,
    ):
        assert (
            HardwareLifecycleManager().transition_device(
                unit,
                HardwareStatus.PROVISIONING,
            )
            is True
        )

    atomic.assert_called_once_with(using="inventory")
    using.assert_called_once_with("inventory")
    save.assert_called_once()
    assert save.call_args.kwargs["using"] == "inventory"


@pytest.mark.django_db
def test_valid_chassis_transition_uses_only_fields_present_on_chassis() -> None:
    """Transition chassis even though it has no WirelessUnit updated_at field."""
    chassis = WirelessChassisFactory(status="discovered")
    manager = HardwareLifecycleManager()

    assert manager.transition_device(chassis, HardwareStatus.PROVISIONING) is True
    chassis.refresh_from_db()
    assert chassis.status == "provisioning"
    assert chassis.last_seen is not None


@pytest.mark.django_db
def test_invalid_transition_does_not_mutate_device() -> None:
    """Reject transitions out of the terminal retired state."""
    unit = WirelessUnitFactory(status="retired", last_seen=None)
    manager = HardwareLifecycleManager()

    assert manager.transition_device(unit, HardwareStatus.ONLINE) is False
    unit.refresh_from_db()
    assert unit.status == "retired"
    assert unit.last_seen is None


@pytest.mark.django_db
def test_transition_validates_locked_state_instead_of_stale_caller_state() -> None:
    """A stale instance cannot resurrect a device after a terminal transition."""
    stale_unit = WirelessUnitFactory(status="online", last_seen=None)
    type(stale_unit).objects.filter(pk=stale_unit.pk).update(status="retired")
    manager = HardwareLifecycleManager()

    assert manager.transition_device(stale_unit, HardwareStatus.OFFLINE) is False
    stale_unit.refresh_from_db()
    assert stale_unit.status == "retired"
    assert stale_unit.last_seen is None


@pytest.mark.parametrize(
    ("method_name", "kwargs", "target_status", "expected_kwargs"),
    [
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
            "mark_offline",
            {"reason": "No heartbeat"},
            "offline",
            {"reason": "No heartbeat"},
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
    manager = HardwareLifecycleManager()

    with patch.object(manager, "transition_device", return_value=True) as transition:
        assert getattr(manager, method_name)(device, **kwargs) is True

    transition.assert_called_once_with(device, target_status, **expected_kwargs)


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


_CHASSIS_MOVES: dict[str, set[str]] = {
    "discovered": {"provisioning", "offline", "retired"},
    "provisioning": {"online", "offline", "discovered"},
    "online": {"degraded", "offline", "maintenance"},
    "degraded": {"online", "offline", "maintenance"},
    "offline": {"online", "degraded", "maintenance", "retired"},
    "maintenance": {"online", "offline", "retired"},
    "retired": set(),
}
_UNIT_MOVES: dict[str, set[str]] = {
    **_CHASSIS_MOVES,
    "online": {"degraded", "idle", "offline", "maintenance"},
    "degraded": {"online", "idle", "offline", "maintenance"},
    "idle": {"online", "offline", "maintenance", "retired"},
    "offline": {"online", "degraded", "idle", "maintenance", "retired"},
}


@pytest.mark.parametrize(
    ("kind", "moves"),
    [(DeviceKind.CHASSIS, _CHASSIS_MOVES), (DeviceKind.UNIT, _UNIT_MOVES)],
)
def test_status_graph_allows_exactly_the_documented_moves(
    kind: DeviceKind,
    moves: dict[str, set[str]],
) -> None:
    """Every ordered status pair is allowed or refused exactly as the graph documents."""
    statuses = set(_UNIT_MOVES)
    for from_status in statuses:
        for to_status in statuses:
            expected = from_status == to_status or to_status in moves.get(from_status, set())
            assert is_valid_transition(kind, from_status, to_status) is expected


def test_chassis_graph_has_no_idle_state() -> None:
    """Only units idle; a chassis cannot enter or leave idle."""
    assert not is_valid_transition(DeviceKind.CHASSIS, "online", "idle")
    assert is_valid_transition(DeviceKind.UNIT, "online", "idle")


def test_ensure_valid_transition_names_the_allowed_moves() -> None:
    """Refusals carry the from/to pair and the moves that would have been allowed."""
    with pytest.raises(
        match=re.escape("discovered → online. Allowed: offline, provisioning, retired"),
    ):
        ensure_valid_transition(DeviceKind.CHASSIS, "discovered", "online")
    with pytest.raises(ValueError, match=re.escape("none (terminal state)")):
        ensure_valid_transition(DeviceKind.CHASSIS, "retired", "online")
    ensure_valid_transition(DeviceKind.CHASSIS, "online", "online")


@pytest.mark.django_db
def test_manager_applies_the_unit_graph_to_units_and_the_chassis_graph_to_chassis() -> None:
    """The manager picks the graph from the device it is given."""
    unit = WirelessUnitFactory(status="online")
    chassis = WirelessChassisFactory(status="online")
    manager = HardwareLifecycleManager()

    assert manager.transition_device(unit, HardwareStatus.IDLE) is True
    assert manager.transition_device(chassis, HardwareStatus.IDLE) is False
    unit.refresh_from_db()
    chassis.refresh_from_db()
    assert (unit.status, chassis.status) == ("idle", "online")
