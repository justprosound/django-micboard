"""Transactional deletion workflow for staged discovery devices."""

from __future__ import annotations

from django.db import transaction
from django.db.models import QuerySet

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.sync.discovery_dtos import DiscoveredDeviceDeletionResult
from micboard.services.sync.discovery_trigger_service import schedule_discovery_on_commit


class DiscoveredDeviceDeletionService:
    """Delete staged devices and request claimed manufacturer reconciliation."""

    @staticmethod
    def delete(queryset: QuerySet[DiscoveredDevice]) -> DiscoveredDeviceDeletionResult:
        """Delete selected rows and schedule one post-commit reconciliation per manufacturer."""
        using = queryset.db
        with transaction.atomic(using=using):
            manufacturer_ids = list(
                queryset.exclude(manufacturer_id__isnull=True)
                .order_by("manufacturer_id")
                .values_list("manufacturer_id", flat=True)
                .distinct()
            )
            deleted_count = queryset.count()
            queryset.delete()
            for manufacturer_id in manufacturer_ids:
                schedule_discovery_on_commit(
                    manufacturer_id=manufacturer_id,
                    scan_cidrs=False,
                    scan_fqdns=False,
                    using=using,
                )

        return DiscoveredDeviceDeletionResult(
            deleted_count=deleted_count,
            scheduled_manufacturers=len(manufacturer_ids),
        )
