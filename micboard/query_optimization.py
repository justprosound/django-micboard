"""Query optimization utilities for django-micboard.

Provides helpers for select_related, prefetch_related, and query analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, TypeVar

from django.db import connection, models
from django.db.models import Prefetch, QuerySet

from micboard.models import (
    Location,
    PerformerAssignment,
    WirelessChassis,
    WirelessUnit,
)

if TYPE_CHECKING:
    pass

_ModelT = TypeVar("_ModelT", bound=models.Model)


class QueryOptimizer:
    """Utility class for query optimization."""

    @staticmethod
    def optimize_receiver_queryset(
        *, queryset: QuerySet[WirelessChassis]
    ) -> QuerySet[WirelessChassis]:
        """Optimize receiver queryset with common relations.

        Args:
            queryset: Base receiver queryset.

        Returns:
            Optimized queryset with select_related and prefetch_related.
        """
        return queryset.select_related(
            "location",
            "manufacturer",
        ).prefetch_related(
            "rf_channels",
        )

    @staticmethod
    def optimize_transmitter_queryset(
        *, queryset: QuerySet[WirelessUnit]
    ) -> QuerySet[WirelessUnit]:
        """Optimize transmitter queryset with common relations.

        Args:
            queryset: Base transmitter queryset.

        Returns:
            Optimized queryset with select_related.
        """
        return queryset.select_related(
            "base_chassis",
            "manufacturer",
        )

    @staticmethod
    def optimize_assignment_queryset(
        *, queryset: QuerySet[PerformerAssignment]
    ) -> QuerySet[PerformerAssignment]:
        """Optimize assignment queryset with relations.

        Args:
            queryset: Base assignment queryset.

        Returns:
            Optimized queryset with select_related.
        """
        return queryset.select_related(
            "performer",
            "wireless_unit",
            "monitoring_group",
        )

    @staticmethod
    def get_receivers_with_assignments() -> QuerySet[WirelessChassis]:
        """Get receivers with optimized assignment prefetch.

        Returns:
            QuerySet of receivers with prefetched assignments.
        """
        assignments_prefetch = Prefetch(
            "wireless_units__performer_assignments",
            queryset=PerformerAssignment.objects.select_related("performer"),
        )

        return WirelessChassis.objects.prefetch_related(assignments_prefetch)

    @staticmethod
    def get_locations_with_device_counts() -> QuerySet[Location]:
        """Get locations with annotated device counts.

        Returns:
            QuerySet of locations with device_count annotation.
        """
        from django.db.models import Count

        return Location.objects.annotate(device_count=Count("wireless_devices"))


class QueryAnalyzer:
    """Analyze and log query performance."""

    @staticmethod
    def get_query_count() -> int:
        """Get number of queries executed so far.

        Returns:
            Query count.
        """
        return len(connection.queries)

    @staticmethod
    def get_queries() -> List[Dict[str, str]]:
        """Get list of executed queries.

        Returns:
            List of query dictionaries with 'sql' and 'time' keys.
        """
        return connection.queries

    @staticmethod
    def print_queries() -> None:
        """Print all executed queries with timing."""
        for i, query in enumerate(connection.queries, 1):
            print(f"\nQuery {i} ({query['time']}s):")
            print(query["sql"])

    @staticmethod
    def get_slow_queries(*, threshold_seconds: float = 0.1) -> List[Dict[str, str]]:
        """Get queries slower than threshold.

        Args:
            threshold_seconds: Time threshold in seconds. Defaults to 0.1.

        Returns:
            List of slow queries.
        """
        return [query for query in connection.queries if float(query["time"]) > threshold_seconds]

    @staticmethod
    def analyze_queryset(*, queryset: QuerySet[Any]) -> Dict[str, Any]:
        """Analyze queryset without executing it.

        Args:
            queryset: QuerySet to analyze.

        Returns:
            Dictionary with query info.
        """
        return {
            "sql": str(queryset.query),
            "model": queryset.model.__name__,
            "ordered": queryset.ordered,
        }


def optimize_bulk_create(*, model_class, objects: List, batch_size: int = 1000):
    """Optimize bulk_create with proper batch size.

    Args:
        model_class: Django model class.
        objects: List of model instances to create.
        batch_size: Batch size for bulk_create. Defaults to 1000.

    Returns:
        List of created instances.
    """
    return model_class.objects.bulk_create(objects, batch_size=batch_size)


def optimize_bulk_update(*, objects: List, fields: List[str], batch_size: int = 1000):
    """Optimize bulk_update with proper batch size.

    Args:
        objects: List of model instances to update.
        fields: List of field names to update.
        batch_size: Batch size for bulk_update. Defaults to 1000.

    Returns:
        Number of objects updated.
    """
    if not objects:
        return 0

    model_class = type(objects[0])
    return model_class.objects.bulk_update(objects, fields, batch_size=batch_size)
