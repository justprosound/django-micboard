"""Behavior contracts for chassis save lifecycle and regulatory preparation."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.services.hardware import chassis_lifecycle_service as lifecycle_service
from micboard.services.hardware import chassis_regulatory_service as regulatory_service
from micboard.services.hardware.dtos import BandPlanInfo, ChassisSaveContext


def _new_chassis(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "_state": SimpleNamespace(adding=True),
        "status": "discovered",
        "is_online": False,
        "last_online_at": None,
        "manufacturer": None,
        "model": "",
        "role": "receiver",
        "band_plan_name": "",
        "band_plan_min_mhz": None,
        "band_plan_max_mhz": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected"),
    [(None, None, False), (470.0, None, False), (534.0, 470.0, False), (470.0, 534.0, True)],
)
def test_band_plan_status_requires_an_ordered_frequency_range(
    minimum: float | None,
    maximum: float | None,
    expected: bool,
) -> None:
    """A usable band plan requires both bounds in ascending order."""
    chassis = SimpleNamespace(band_plan_min_mhz=minimum, band_plan_max_mhz=maximum)

    assert regulatory_service.get_band_plan_status(chassis) is expected


def test_band_plan_detection_fails_closed_without_a_manufacturer() -> None:
    """Do not infer vendor-specific ranges without a manufacturer."""
    chassis = SimpleNamespace(manufacturer=None, model="ULXD4Q")

    result = regulatory_service.detect_band_plan_from_api_data(chassis, api_band_value="G50")

    assert result == BandPlanInfo(message="Manufacturer not set")


@pytest.mark.parametrize(
    ("api_value", "api_detection", "model_detection", "expected_source"),
    [("G50", "G50", None, "api"), (None, None, "G50", "model")],
)
def test_band_plan_detection_uses_api_then_model_fallback(
    api_value: str | None,
    api_detection: str | None,
    model_detection: str | None,
    expected_source: str,
) -> None:
    """Prefer API evidence and fall back to a recognized model code."""
    chassis = SimpleNamespace(
        manufacturer=SimpleNamespace(code="SHURE"),
        model="ULXD4Q",
    )
    with (
        patch(
            "micboard.models.band_plans.detect_band_plan_from_api_string",
            return_value=api_detection,
        ),
        patch(
            "micboard.models.band_plans.get_band_plan_from_model_code",
            return_value=model_detection,
        ),
        patch(
            "micboard.models.band_plans.get_band_plan",
            return_value={"min_mhz": 470.0, "max_mhz": 534.0},
        ),
    ):
        result = regulatory_service.detect_band_plan_from_api_data(
            chassis, api_band_value=api_value
        )

    assert result.name == "G50"
    assert result.min_mhz == 470.0
    assert result.max_mhz == 534.0
    assert result.source == expected_source


def test_band_plan_detection_reports_when_no_strategy_matches() -> None:
    """Return an explicit empty outcome when API and model evidence fail."""
    chassis = SimpleNamespace(
        manufacturer=SimpleNamespace(code="SHURE"),
        model="Unknown",
    )
    with (
        patch("micboard.models.band_plans.detect_band_plan_from_api_string", return_value=None),
        patch("micboard.models.band_plans.get_band_plan_from_model_code", return_value=None),
    ):
        result = regulatory_service.detect_band_plan_from_api_data(
            chassis, api_band_value="Unknown"
        )

    assert result.name is None
    assert result.source is None
    assert result.message == "No band plan detected from API or model"


def test_apply_detected_band_plan_mutates_only_successful_detection() -> None:
    """Copy all detected fields while leaving an unknown chassis unchanged."""
    chassis = SimpleNamespace(
        band_plan_name="Existing",
        band_plan_min_mhz=100.0,
        band_plan_max_mhz=200.0,
    )
    with patch.object(
        regulatory_service,
        "detect_band_plan_from_api_data",
        return_value=BandPlanInfo(),
    ):
        assert regulatory_service.apply_detected_band_plan(chassis) is False
    assert chassis.band_plan_name == "Existing"

    with patch.object(
        regulatory_service,
        "detect_band_plan_from_api_data",
        return_value=BandPlanInfo(name="G50", min_mhz=470.0, max_mhz=534.0),
    ):
        assert regulatory_service.apply_detected_band_plan(chassis, api_band_value="G50") is True
    assert (chassis.band_plan_name, chassis.band_plan_min_mhz, chassis.band_plan_max_mhz) == (
        "G50",
        470.0,
        534.0,
    )


@pytest.mark.parametrize(
    ("status", "expected_online", "expected_fields"),
    [("online", True, {"is_online", "last_online_at"}), ("discovered", False, set())],
)
def test_new_chassis_lifecycle_derives_operational_fields(
    status: str,
    expected_online: bool,
    expected_fields: set[str],
) -> None:
    """Initialize online metadata only for a newly operational chassis."""
    chassis = _new_chassis(status=status)

    context = lifecycle_service.prepare_chassis_for_save(chassis)

    assert chassis.is_online is expected_online
    assert context == ChassisSaveContext(created=True, update_fields=expected_fields)


def test_existing_chassis_rejects_an_invalid_transition() -> None:
    """Validate transitions against the locked persisted status."""
    previous = SimpleNamespace(
        status="online",
        is_online=True,
        last_online_at=timezone.now(),
        total_uptime_minutes=0,
    )
    manager = Mock()
    manager.using.return_value.only.return_value.get.return_value = previous

    class Chassis:
        objects = manager

    chassis = Chassis()
    chassis._state = SimpleNamespace(adding=False)
    chassis.pk = 17
    chassis.status = "retired"
    chassis.manufacturer = None
    chassis.model = ""

    with pytest.raises(ValueError, match="Invalid status transition"):
        lifecycle_service.prepare_chassis_for_save(chassis, using="inventory")
    manager.using.assert_called_once_with("inventory")


def test_existing_chassis_records_uptime_when_leaving_operational_state() -> None:
    """Persist offline metadata and non-negative elapsed uptime."""
    now = timezone.now()
    previous = SimpleNamespace(
        status="online",
        is_online=True,
        last_online_at=now - timedelta(minutes=12),
        total_uptime_minutes=8,
    )
    manager = Mock()
    manager.using.return_value.only.return_value.get.return_value = previous

    class Chassis:
        objects = manager

    chassis = Chassis()
    chassis._state = SimpleNamespace(adding=False)
    chassis.pk = 18
    chassis.status = "offline"
    chassis.is_online = True
    chassis.manufacturer = None
    chassis.model = ""
    with patch.object(lifecycle_service.timezone, "now", return_value=now):
        context = lifecycle_service.prepare_chassis_for_save(chassis)

    assert chassis.is_online is False
    assert chassis.last_offline_at == now
    assert chassis.total_uptime_minutes == 20
    assert context.status_changed is True
    assert context.update_fields == {
        "is_online",
        "last_offline_at",
        "total_uptime_minutes",
    }


def test_existing_chassis_same_status_has_no_lifecycle_mutation() -> None:
    """Avoid timestamps and update fields when the persisted status is unchanged."""
    previous = SimpleNamespace(
        status="offline",
        is_online=False,
        last_online_at=None,
        total_uptime_minutes=4,
    )
    manager = Mock()
    manager.using.return_value.only.return_value.get.return_value = previous

    class Chassis:
        objects = manager

    chassis = Chassis()
    chassis._state = SimpleNamespace(adding=False)
    chassis.pk = 19
    chassis.status = "offline"
    chassis.manufacturer = None
    chassis.model = ""

    context = lifecycle_service.prepare_chassis_for_save(chassis)

    assert context.status_changed is False
    assert context.update_fields == set()


def test_existing_chassis_records_online_timestamp_on_recovery() -> None:
    """Mark a persisted offline chassis online when it recovers."""
    now = timezone.now()
    previous = SimpleNamespace(
        status="offline",
        is_online=False,
        last_online_at=None,
        total_uptime_minutes=4,
    )
    manager = Mock()
    manager.using.return_value.only.return_value.get.return_value = previous

    class Chassis:
        objects = manager

    chassis = Chassis()
    chassis._state = SimpleNamespace(adding=False)
    chassis.pk = 20
    chassis.status = "online"
    chassis.manufacturer = None
    chassis.model = ""
    with patch.object(lifecycle_service.timezone, "now", return_value=now):
        context = lifecycle_service.prepare_chassis_for_save(chassis)

    assert chassis.is_online is True
    assert chassis.last_online_at == now
    assert context.update_fields == {"is_online", "last_online_at"}


def test_chassis_specs_parse_named_band_plan_and_derive_missing_role() -> None:
    """Apply registry specifications and parse explicit band-plan ranges."""
    chassis = _new_chassis(
        manufacturer=SimpleNamespace(code="SHURE"),
        model="ULXD4Q",
        role="",
        band_plan_name="G50 (470-534 MHz)",
    )
    with (
        patch(
            "micboard.services.core.device_specs.DeviceSpecService.apply_specs_to_chassis"
        ) as apply_specs,
        patch("micboard.models.device_specs.get_device_role", return_value="receiver"),
        patch(
            "micboard.models.band_plans.parse_band_plan_from_name",
            return_value={"min_mhz": 470.0, "max_mhz": 534.0},
        ),
    ):
        lifecycle_service.prepare_chassis_for_save(chassis)

    apply_specs.assert_called_once_with(chassis)
    assert chassis.role == "receiver"
    assert (chassis.band_plan_min_mhz, chassis.band_plan_max_mhz) == (470.0, 534.0)


@pytest.mark.parametrize(
    ("detected", "band_plan", "expected_name", "expected_bounds"),
    [
        (None, None, "", (None, None)),
        ("G50", None, "G50", (None, None)),
        ("G50", {"min_mhz": 470.0, "max_mhz": 534.0}, "G50", (470.0, 534.0)),
    ],
)
def test_chassis_specs_fill_band_plan_from_model_when_available(
    detected: str | None,
    band_plan: dict[str, float] | None,
    expected_name: str,
    expected_bounds: tuple[float | None, float | None],
) -> None:
    """Use model lookup directly while preserving partial detection evidence."""
    chassis = _new_chassis(
        manufacturer=SimpleNamespace(code="SHURE"),
        model="ULXD4Q",
    )
    with (
        patch("micboard.services.core.device_specs.DeviceSpecService.apply_specs_to_chassis"),
        patch(
            "micboard.models.band_plans.get_band_plan_from_model_code",
            return_value=detected,
        ),
        patch("micboard.models.band_plans.get_band_plan", return_value=band_plan),
    ):
        lifecycle_service.prepare_chassis_for_save(chassis)

    assert chassis.band_plan_name == expected_name
    assert (chassis.band_plan_min_mhz, chassis.band_plan_max_mhz) == expected_bounds


def test_persisted_chassis_broadcast_handles_deleted_and_current_rows() -> None:
    """Broadcast only a final committed chassis row from the selected database."""
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    queryset = Mock()
    with patch.object(WirelessChassis._default_manager, "using", return_value=queryset):
        queryset.select_related.return_value.get.side_effect = WirelessChassis.DoesNotExist
        lifecycle_service._broadcast_persisted_chassis_status(chassis_id=17, using="inventory")

    chassis = SimpleNamespace(
        pk=18,
        manufacturer=SimpleNamespace(code="vendor"),
        status="online",
        is_online=True,
    )
    queryset.select_related.return_value.get.side_effect = None
    queryset.select_related.return_value.get.return_value = chassis
    with (
        patch.object(WirelessChassis._default_manager, "using", return_value=queryset),
        patch(
            "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
        ) as broadcast,
    ):
        lifecycle_service._broadcast_persisted_chassis_status(chassis_id=18, using="inventory")

    broadcast.assert_called_once_with(
        service_code="vendor",
        device_id=18,
        device_type="SimpleNamespace",
        status="online",
        is_active=True,
    )


def test_status_broadcast_scheduling_coalesces_duplicate_callbacks() -> None:
    """Register one robust commit callback for each chassis transaction."""
    chassis = SimpleNamespace(pk=17)
    existing = Mock()
    existing._micboard_chassis_status_id = 17
    connection = SimpleNamespace(run_on_commit=[(set(), existing, True)])
    with (
        patch.object(lifecycle_service.transaction, "get_connection", return_value=connection),
        patch.object(lifecycle_service.transaction, "on_commit") as on_commit,
    ):
        lifecycle_service._schedule_status_broadcast(chassis, using="inventory")
    on_commit.assert_not_called()

    connection.run_on_commit = []
    with (
        patch.object(lifecycle_service.transaction, "get_connection", return_value=connection),
        patch.object(lifecycle_service.transaction, "on_commit") as on_commit,
    ):
        lifecycle_service._schedule_status_broadcast(chassis, using="inventory")
    callback = on_commit.call_args.args[0]
    assert callback._micboard_chassis_status_id == 17
    assert on_commit.call_args.kwargs == {"using": "inventory", "robust": True}


def test_finalize_chassis_save_emits_audit_and_schedules_broadcast() -> None:
    """Status changes emit one audit entry and one committed broadcast."""
    chassis = SimpleNamespace(pk=17, status="online")
    with (
        patch("micboard.services.maintenance.audit.AuditService.log_activity") as audit,
        patch.object(lifecycle_service, "_schedule_status_broadcast") as schedule,
    ):
        lifecycle_service.finalize_chassis_save(
            chassis,
            ChassisSaveContext(created=False, old_status="offline"),
            using="inventory",
        )
        lifecycle_service.finalize_chassis_save(
            chassis,
            ChassisSaveContext(
                created=False,
                old_status="offline",
                status_changed=True,
            ),
            using="inventory",
        )

    audit.assert_called_once_with(
        activity_type="hardware",
        operation="status_change",
        summary="Chassis status changed: offline → online",
        obj=chassis,
        old_values={"status": "offline"},
        new_values={"status": "online"},
        using="inventory",
    )
    schedule.assert_called_once_with(chassis, using="inventory")
