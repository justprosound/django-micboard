"""Utility functions for services layer.

Common utilities for service operations including pagination, filtering, and data transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """Result container for paginated queries."""

    items: list[T]
    total_count: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total_count + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        """Check if next page exists."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if previous page exists."""
        return self.page > 1


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
        """Total number of items changed."""
        return self.items_added + self.items_updated + self.items_removed

    def add_error(self, *, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)


def paginate_queryset(*, queryset, page: int = 1, page_size: int = 20) -> PaginatedResult:
    """Paginate a Django QuerySet.

    Args:
        queryset: Django QuerySet to paginate.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        PaginatedResult with items and pagination metadata.
    """
    total_count = queryset.count()
    offset = (page - 1) * page_size

    items = list(queryset[offset : offset + page_size])

    return PaginatedResult(items=items, total_count=total_count, page=page, page_size=page_size)


def filter_by_search(*, queryset, search_fields: list[str], query: str) -> Any:
    """Filter a queryset by search query across multiple fields.

    Args:
        queryset: Django QuerySet to filter.
        search_fields: List of field names to search (supports __lookup).
        query: Search query string.

    Returns:
        Filtered QuerySet.

    Example:
        devices = filter_by_search(
            queryset=WirelessChassis.objects.all(),
            search_fields=['name', 'ip', 'model'],
            query='micboard'
        )
    """
    from django.db.models import Q

    if not query:
        return queryset

    q_objects = Q()
    for field in search_fields:
        q_objects |= Q(**{f"{field}__icontains": query})

    return queryset.filter(q_objects)


def get_model_changes(*, instance, old_values: dict[str, Any]) -> dict[str, Any]:
    """Get changed fields and their new values.

    Args:
        instance: Model instance to check.
        old_values: Dictionary of previous values.

    Returns:
        Dictionary of changed fields: {field: new_value}.
    """
    changes = {}
    for field, old_value in old_values.items():
        new_value = getattr(instance, field)
        if new_value != old_value:
            changes[field] = new_value

    return changes


def merge_sync_results(*results: SyncResult) -> SyncResult:
    """Merge multiple sync results into one.

    Args:
        results: Variable number of SyncResult objects.

    Returns:
        Merged SyncResult.
    """
    merged = SyncResult(
        success=all(r.success for r in results),
        items_added=sum(r.items_added for r in results),
        items_updated=sum(r.items_updated for r in results),
        items_removed=sum(r.items_removed for r in results),
        errors=[err for r in results for err in r.errors],
    )
    return merged
