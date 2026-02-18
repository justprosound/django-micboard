"""Synchronization utilities for service layer.

Provides SyncResult, merge_sync_results, and get_model_changes for sync operations and model change detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SyncResult:
    """Result container for synchronization operations."""

    success: bool
    items_added: int
    items_updated: int
    items_removed: int
    errors: list[str]

    @property
    def total_changes(self) -> int:
        return self.items_added + self.items_updated + self.items_removed

    def add_error(self, *, message: str) -> None:
        self.errors.append(message)


def get_model_changes(*, instance, old_values: dict[str, Any]) -> dict[str, Any]:
    changes = {}
    for field, old_value in old_values.items():
        new_value = getattr(instance, field)
        if new_value != old_value:
            changes[field] = new_value
    return changes


def merge_sync_results(*results: SyncResult) -> SyncResult:
    merged = SyncResult(
        success=all(r.success for r in results),
        items_added=sum(r.items_added for r in results),
        items_updated=sum(r.items_updated for r in results),
        items_removed=sum(r.items_removed for r in results),
        errors=[err for r in results for err in r.errors],
    )
    return merged
