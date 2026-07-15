"""Validated commands for performer assignment writes."""

from typing import Literal

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

AssignmentPriority = Literal["low", "normal", "high", "critical"]


class CreatePerformerAssignment(PydanticBaseDTO):
    """Data required to bind a performer, wireless unit, and monitoring group."""

    performer_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    priority: AssignmentPriority = "normal"
    notes: str = Field(default="", max_length=10_000)
    alert_on_battery_low: bool | None = None
    alert_on_signal_loss: bool | None = None
    alert_on_audio_low: bool | None = None
    alert_on_hardware_offline: bool | None = None
    is_active: bool = True


class UpdatePerformerAssignment(PydanticBaseDTO):
    """Partial assignment update with omission distinct from false or blank."""

    assignment_id: int = Field(gt=0)
    priority: AssignmentPriority | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    is_active: bool | None = None
    alert_on_battery_low: bool | None = None
    alert_on_signal_loss: bool | None = None
    alert_on_audio_low: bool | None = None
    alert_on_hardware_offline: bool | None = None
