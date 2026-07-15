"""Performer assignment validation and default contracts."""

from typing import get_args

from django.core.exceptions import ValidationError

import pytest

from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import (
    AssignmentPriority,
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessUnitFactory
from tests.factories.monitoring import (
    MonitoringGroupFactory,
    PerformerAssignmentFactory,
    PerformerFactory,
)

pytestmark = pytest.mark.django_db


def test_assignment_priority_command_matches_model_choices() -> None:
    """DTO validation cannot drift from the model's supported priority values."""
    assert set(get_args(AssignmentPriority)) == {
        value for value, _label in PerformerAssignment.PRIORITY_CHOICES
    }


def test_create_assignment_preserves_model_alert_defaults() -> None:
    """Omitted service options retain the model's documented defaults."""
    user = UserFactory(is_staff=True, is_superuser=True)

    assignment = PerformerAssignmentService.create_assignment(
        command=CreatePerformerAssignment(
            performer_id=PerformerFactory().pk,
            unit_id=WirelessUnitFactory().pk,
            group_id=MonitoringGroupFactory().pk,
        ),
        user=user,
    )

    assert assignment.alert_on_battery_low is True
    assert assignment.alert_on_signal_loss is True
    assert assignment.alert_on_audio_low is False
    assert assignment.alert_on_hardware_offline is True


def test_create_assignment_rejects_invalid_priority() -> None:
    """Direct service callers cannot persist values outside model choices."""
    user = UserFactory(is_staff=True, is_superuser=True)
    command = CreatePerformerAssignment.model_construct(
        performer_id=PerformerFactory().pk,
        unit_id=WirelessUnitFactory().pk,
        group_id=MonitoringGroupFactory().pk,
        priority="urgent",
        notes="",
        alert_on_battery_low=None,
        alert_on_signal_loss=None,
        alert_on_audio_low=None,
        alert_on_hardware_offline=None,
        is_active=True,
    )

    with pytest.raises(ValidationError, match="not a valid choice"):
        PerformerAssignmentService.create_assignment(command=command, user=user)


def test_create_assignment_applies_explicit_alert_preferences() -> None:
    """Explicit false values must override model defaults instead of being treated as omitted."""
    user = UserFactory(is_staff=True, is_superuser=True)

    assignment = PerformerAssignmentService.create_assignment(
        command=CreatePerformerAssignment(
            performer_id=PerformerFactory().pk,
            unit_id=WirelessUnitFactory().pk,
            group_id=MonitoringGroupFactory().pk,
            alert_on_battery_low=False,
            alert_on_signal_loss=False,
            alert_on_audio_low=True,
            alert_on_hardware_offline=False,
        ),
        user=user,
    )

    assert assignment.alert_on_battery_low is False
    assert assignment.alert_on_signal_loss is False
    assert assignment.alert_on_audio_low is True
    assert assignment.alert_on_hardware_offline is False


def test_update_assignment_applies_false_and_blank_values() -> None:
    """Partial updates distinguish explicit false and blank values from omitted fields."""
    user = UserFactory(is_staff=True, is_superuser=True)
    assignment = PerformerAssignmentFactory(notes="existing", is_active=True)

    updated = PerformerAssignmentService.update_assignment(
        command=UpdatePerformerAssignment(
            assignment_id=assignment.pk,
            priority="critical",
            notes="",
            is_active=False,
            alert_on_battery_low=False,
        ),
        user=user,
    )

    assert updated.priority == "critical"
    assert updated.notes == ""
    assert updated.is_active is False
    assert updated.alert_on_battery_low is False


@pytest.mark.parametrize("page", ["invalid", 0, -3, None])
def test_visible_assignment_rows_normalize_invalid_pages(page: int | str | None) -> None:
    """Live-refresh slices normalize malformed and non-positive page values to page one."""
    user = UserFactory(is_staff=True, is_superuser=True)
    assignment = PerformerAssignmentFactory()

    rows = list(PerformerAssignmentService.get_visible_assignment_rows(user=user, page=page))

    assert rows == [assignment]


def test_preferred_assignment_queries_materialize_one_row_per_unit(
    django_assert_num_queries,
) -> None:
    """SQL ranking discards lower-priority candidates before Python materialization."""
    user = UserFactory(is_staff=True, is_superuser=True)
    first_unit = WirelessUnitFactory(serial_number="preferred-first")
    second_unit = WirelessUnitFactory(serial_number="preferred-second")
    for _ in range(40):
        PerformerAssignmentFactory(wireless_unit=first_unit, priority="low")
    expected_first = PerformerAssignmentFactory(
        wireless_unit=first_unit,
        priority="critical",
    )
    expected_second = PerformerAssignmentFactory(
        wireless_unit=second_unit,
        priority="high",
    )
    PerformerAssignmentFactory(
        wireless_unit=second_unit,
        priority="critical",
        is_active=False,
    )

    with django_assert_num_queries(1):
        by_unit = list(
            PerformerAssignmentService.get_preferred_active_assignments_for_units(
                user=user,
                unit_ids={first_unit.pk, second_unit.pk},
            )
        )
    with django_assert_num_queries(1):
        by_serial = list(
            PerformerAssignmentService.get_preferred_active_assignments_for_serials(
                user=user,
                serial_numbers={first_unit.serial_number, second_unit.serial_number},
            )
        )

    assert [assignment.pk for assignment in by_unit] == [
        expected_first.pk,
        expected_second.pk,
    ]
    assert [assignment.pk for assignment in by_serial] == [
        expected_first.pk,
        expected_second.pk,
    ]


def test_preferred_assignment_queries_short_circuit_empty_inputs(
    django_assert_num_queries,
) -> None:
    """Empty bounded projections avoid issuing assignment queries."""
    user = UserFactory(is_staff=True, is_superuser=True)

    with django_assert_num_queries(0):
        assert (
            list(
                PerformerAssignmentService.get_preferred_active_assignments_for_units(
                    user=user,
                    unit_ids=[],
                )
            )
            == []
        )
        assert (
            list(
                PerformerAssignmentService.get_preferred_active_assignments_for_serials(
                    user=user,
                    serial_numbers=[],
                )
            )
            == []
        )


@pytest.mark.parametrize("operation", ["delete_assignment", "deactivate_assignment"])
def test_assignment_terminal_mutations_succeed(operation: str) -> None:
    """Authorized terminal mutations report success and persist their documented outcome."""
    user = UserFactory(is_staff=True, is_superuser=True)
    assignment = PerformerAssignmentFactory(is_active=True)

    mutate = getattr(PerformerAssignmentService, operation)
    assert mutate(assignment_id=assignment.pk, user=user) is True

    if operation == "delete_assignment":
        assert not PerformerAssignment.objects.filter(pk=assignment.pk).exists()
    else:
        assignment.refresh_from_db()
        assert assignment.is_active is False


@pytest.mark.parametrize("operation", ["delete_assignment", "deactivate_assignment"])
def test_assignment_terminal_mutations_report_missing_rows(operation: str) -> None:
    """Missing or invisible rows retain the public false-result contract."""
    user = UserFactory(is_staff=True, is_superuser=True)

    mutate = getattr(PerformerAssignmentService, operation)

    assert mutate(assignment_id=999_999, user=user) is False
