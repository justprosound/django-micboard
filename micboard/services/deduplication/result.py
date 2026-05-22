from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis


class DeduplicationResult:
    """Result of device deduplication check."""

    def __init__(
        self,
        is_duplicate: bool = False,
        is_new: bool = False,
        is_moved: bool = False,
        is_conflict: bool = False,
        existing_device: WirelessChassis | None = None,
        conflict_type: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.is_duplicate = is_duplicate
        self.is_new = is_new
        self.is_moved = is_moved
        self.is_conflict = is_conflict
        self.existing_device = existing_device
        self.conflict_type = conflict_type
        self.details = details or {}

    def __repr__(self) -> str:
        if self.is_new:
            return "DeduplicationResult(new_device)"
        if self.is_moved:
            return f"DeduplicationResult(moved: {self.conflict_type})"
        if self.is_duplicate:
            return f"DeduplicationResult(duplicate: {self.conflict_type})"
        if self.is_conflict:
            return f"DeduplicationResult(conflict: {self.conflict_type})"
        return "DeduplicationResult(unknown)"
