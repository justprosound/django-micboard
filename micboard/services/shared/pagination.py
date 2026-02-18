"""Pagination utilities for service layer.

Provides PaginatedResult, paginate_queryset, and filter_by_search for paginating and searching querysets.
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
        return (self.total_count + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1


def paginate_queryset(*, queryset, page: int = 1, page_size: int = 20) -> PaginatedResult:
    total_count = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return PaginatedResult(items=items, total_count=total_count, page=page, page_size=page_size)


def filter_by_search(*, queryset, search_fields: list[str], query: str) -> Any:
    from django.db.models import Q

    if not query:
        return queryset
    q_objects = Q()
    for field in search_fields:
        q_objects |= Q(**{f"{field}__icontains": query})
    return queryset.filter(q_objects)
