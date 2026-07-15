"""Validated deduplication outcome DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.shared.base_dto import PydanticBaseDTO


class DeduplicationOutcome(StrEnum):
    """Mutually exclusive device identity classifications."""

    NEW = "new"
    DUPLICATE = "duplicate"
    MOVED = "moved"
    CONFLICT = "conflict"


class DeduplicationResult(PydanticBaseDTO):
    """Validated result of one device identity check."""

    outcome: DeduplicationOutcome
    existing_device: WirelessChassis | None = None
    conflict_type: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_outcome_context(self) -> Self:
        """Require outcome-specific identity context and reject contradictions."""
        if (
            self.outcome in {DeduplicationOutcome.DUPLICATE, DeduplicationOutcome.MOVED}
            and self.existing_device is None
        ):
            raise ValueError(f"{self.outcome} outcomes require an existing device")
        if self.outcome == DeduplicationOutcome.NEW:
            if self.existing_device is not None or self.conflict_type is not None:
                raise ValueError("new outcomes cannot reference an existing conflict")
        elif self.conflict_type is None:
            raise ValueError(f"{self.outcome} outcomes require a conflict type")
        return self

    @property
    def is_new(self) -> bool:
        """Return whether the identity is unseen."""
        return self.outcome == DeduplicationOutcome.NEW

    @property
    def is_duplicate(self) -> bool:
        """Return whether the identity matches without movement."""
        return self.outcome == DeduplicationOutcome.DUPLICATE

    @property
    def is_moved(self) -> bool:
        """Return whether a durable identity changed address."""
        return self.outcome == DeduplicationOutcome.MOVED

    @property
    def is_conflict(self) -> bool:
        """Return whether supplied identity keys disagree."""
        return self.outcome == DeduplicationOutcome.CONFLICT

    @classmethod
    def new(cls) -> Self:
        """Create a new-device outcome."""
        return cls(outcome=DeduplicationOutcome.NEW)

    @classmethod
    def duplicate(
        cls,
        existing_device: WirelessChassis,
        *,
        conflict_type: str = "duplicate",
        details: dict[str, Any] | None = None,
    ) -> Self:
        """Create a duplicate-device outcome."""
        return cls(
            outcome=DeduplicationOutcome.DUPLICATE,
            existing_device=existing_device,
            conflict_type=conflict_type,
            details=details or {},
        )

    @classmethod
    def moved(
        cls,
        existing_device: WirelessChassis,
        *,
        conflict_type: str,
        details: dict[str, Any] | None = None,
    ) -> Self:
        """Create a moved-device outcome."""
        return cls(
            outcome=DeduplicationOutcome.MOVED,
            existing_device=existing_device,
            conflict_type=conflict_type,
            details=details or {},
        )

    @classmethod
    def conflict(
        cls,
        *,
        conflict_type: str,
        existing_device: WirelessChassis | None = None,
        details: dict[str, Any] | None = None,
    ) -> Self:
        """Create an identity-conflict outcome."""
        return cls(
            outcome=DeduplicationOutcome.CONFLICT,
            existing_device=existing_device,
            conflict_type=conflict_type,
            details=details or {},
        )

    def __repr__(self) -> str:
        if self.is_new:
            return "DeduplicationResult(new_device)"
        return f"DeduplicationResult({self.outcome}: {self.conflict_type})"
