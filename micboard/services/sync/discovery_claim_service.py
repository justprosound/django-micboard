"""Database-backed ownership for manufacturer discovery synchronization."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from django.db import transaction
from django.utils import timezone

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryJob
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary

DISCOVERY_SYNC_LEASE_SECONDS = 60 * 60
STALE_DISCOVERY_NOTE = "Discovery synchronization lease expired"


class DiscoverySyncClaimService:
    """Claim and finalize per-manufacturer synchronization jobs atomically."""

    @staticmethod
    def claim(manufacturer_id: int) -> tuple[Manufacturer, DiscoveryJob] | None:
        """Create a running job unless a non-stale synchronization already owns the claim."""
        now = timezone.now()
        stale_before = now - timedelta(seconds=DISCOVERY_SYNC_LEASE_SECONDS)

        with transaction.atomic():
            manufacturer = Manufacturer.objects.select_for_update().get(
                pk=manufacturer_id,
                is_active=True,
            )
            running_jobs = list(
                DiscoveryJob.objects.select_for_update()
                .filter(
                    manufacturer=manufacturer,
                    action="sync",
                    status="running",
                )
                .order_by("pk")
            )
            stale_job_ids = [
                job.pk for job in running_jobs if (job.started_at or job.created_at) <= stale_before
            ]
            if stale_job_ids:
                DiscoveryJob.objects.filter(
                    pk__in=stale_job_ids,
                    status="running",
                ).update(
                    status="failed",
                    finished_at=now,
                    note=STALE_DISCOVERY_NOTE,
                )

            if len(stale_job_ids) != len(running_jobs):
                return None

            job = DiscoveryJob.objects.create(
                manufacturer=manufacturer,
                action="sync",
                status="running",
                started_at=now,
            )
            return manufacturer, job

    @staticmethod
    def finalize(job: DiscoveryJob, summary: DiscoverySyncSummary) -> bool:
        """Finalize only the running job that still owns its manufacturer claim."""
        terminal_status: Literal["failed", "success"] = "failed" if summary.errors else "success"
        submitted = summary.scanned_ips_submitted + summary.missing_ips_submitted

        with transaction.atomic():
            Manufacturer.objects.select_for_update().only("pk").get(pk=job.manufacturer_id)
            claimed_job = DiscoveryJob.objects.select_for_update().get(
                pk=job.pk,
                manufacturer_id=job.manufacturer_id,
            )
            if claimed_job.status != "running":
                return False

            claimed_job.status = terminal_status
            claimed_job.finished_at = timezone.now()
            claimed_job.items_scanned = submitted
            claimed_job.items_submitted = submitted
            claimed_job.note = "; ".join(summary.errors)[:1024]
            claimed_job.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "items_scanned",
                    "items_submitted",
                    "note",
                ]
            )

        summary.status = terminal_status
        return True
