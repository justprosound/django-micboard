"""Performer assignment validation and default contracts."""

from typing import get_args

from django.core.exceptions import ValidationError

import pytest

from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import (
    AssignmentPriority,
    CreatePerformerAssignment,
)
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessUnitFactory
from tests.factories.monitoring import MonitoringGroupFactory, PerformerFactory

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
