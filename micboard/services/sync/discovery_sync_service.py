"""Orchestrate a complete manufacturer discovery synchronization."""

from __future__ import annotations

import logging
from typing import Any

from micboard.discovery.limits import (
    DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    DISCOVERY_SUBMISSION_BATCH_SIZE,
    clamp_candidate_limit,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryJob
from micboard.services.common.base.plugin import ManufacturerPlugin
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.notification.device_broadcast_service import (
    DeviceSnapshotBroadcastService,
)
from micboard.services.sync.discovery_candidate_source_service import (
    DiscoveryCandidateSourceService,
)
from micboard.services.sync.discovery_claim_service import DiscoverySyncClaimService
from micboard.services.sync.discovery_configuration_service import (
    DiscoveryConfigurationService,
)
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_queue_service import DiscoveryQueueService
from micboard.services.sync.discovery_service import DiscoveryService
from micboard.services.sync.discovery_utils import get_manufacturer_plugin_instance
from micboard.services.sync.polling_dtos import ManufacturerPollLimits
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

CLAIM_FAILURE_REASON = "discovery_claim_failed"
SYNC_FAILURE_REASON = "discovery_workflow_failed"
FINALIZATION_FAILURE_REASON = "discovery_finalization_failed"
SUPPORTED_MODELS_INCOMPLETE_REASON = "supported_models_payload_incomplete"
CONFIG_ENTRIES_INCOMPLETE_REASON = "discovery_configuration_input_incomplete"
INVENTORY_SOURCES_INCOMPLETE_REASON = "discovery_inventory_sources_incomplete"
SCAN_SOURCES_INCOMPLETE_REASON = "discovery_scan_sources_incomplete"
MANUFACTURER_INACTIVE_REASON = "manufacturer_inactive"
MANUFACTURER_STATUS_CHECK_FAILURE_REASON = "manufacturer_status_check_failed"


class DiscoverySyncService:
    """Synchronize vendor inventory, local candidates, and the review queue."""

    def __init__(
        self,
        *,
        discovery_service: DiscoveryService | None = None,
        claim_service: DiscoverySyncClaimService | None = None,
    ) -> None:
        """Create the orchestrator with optional service dependencies."""
        self.discovery_service = (
            discovery_service if discovery_service is not None else DiscoveryService()
        )
        self.claim_service = (
            claim_service if claim_service is not None else DiscoverySyncClaimService()
        )

    def run(
        self,
        manufacturer_id: int,
        *,
        add_cidrs: list[str] | None = None,
        add_fqdns: list[str] | None = None,
        scan_cidrs: bool = False,
        scan_fqdns: bool = False,
        max_hosts: int = DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    ) -> dict[str, Any]:
        """Run one synchronization and return its stable task-result mapping."""
        summary = DiscoverySyncSummary(manufacturer=manufacturer_id)
        try:
            claim = self.claim_service.claim(manufacturer_id)
        except Manufacturer.DoesNotExist:
            message = f"Manufacturer {manufacturer_id} not found"
            logger.error(message)
            summary.record_error(message)
            return summary.model_dump()
        except Exception as exc:
            logger.exception(
                "Could not claim discovery synchronization for %s",
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            summary.record_error(CLAIM_FAILURE_REASON)
            return summary.model_dump()
        if claim is None:
            summary.record_error(
                f"Discovery synchronization already running for manufacturer {manufacturer_id}"
            )
            return summary.model_dump()

        manufacturer, job = claim
        return self._run_claimed(
            manufacturer,
            job,
            summary,
            add_cidrs=add_cidrs,
            add_fqdns=add_fqdns,
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
            max_hosts=max_hosts,
        )

    def _run_claimed(
        self,
        manufacturer: Manufacturer,
        job: DiscoveryJob,
        summary: DiscoverySyncSummary,
        *,
        add_cidrs: list[str] | None,
        add_fqdns: list[str] | None,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ) -> dict[str, Any]:
        """Execute one synchronization after its database claim transaction has closed."""
        workflow_completed = False
        if self._record_current_activation_state(manufacturer, summary):
            try:
                self._execute_claimed_workflow(
                    manufacturer,
                    summary,
                    add_cidrs=add_cidrs,
                    add_fqdns=add_fqdns,
                    scan_cidrs=scan_cidrs,
                    scan_fqdns=scan_fqdns,
                    max_hosts=max_hosts,
                )
                workflow_completed = True
            except Exception as exc:
                logger.exception(
                    "Discovery synchronization failed for %s",
                    manufacturer.code,
                    exc_info=sanitized_exception_info(exc),
                )
                summary.record_error(SYNC_FAILURE_REASON)

        try:
            claim_finalized = self.claim_service.finalize(job, summary)
        except Exception as exc:
            logger.exception(
                "Could not finalize discovery synchronization for %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            summary.record_error(FINALIZATION_FAILURE_REASON)
            return summary.model_dump()
        if not claim_finalized:
            summary.record_error("Discovery synchronization claim expired before finalization")
            return summary.model_dump()
        if workflow_completed:
            self.broadcast_results(manufacturer)
        return summary.model_dump()

    @staticmethod
    def _record_current_activation_state(
        manufacturer: Manufacturer,
        summary: DiscoverySyncSummary,
    ) -> bool:
        """Fail closed and record a stable reason when current activation cannot permit work."""
        try:
            manufacturer_active = ManufacturerActivationService.is_active(manufacturer.pk)
        except Exception as exc:
            logger.exception(
                "Could not revalidate manufacturer ID %s before discovery synchronization",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            summary.record_error(MANUFACTURER_STATUS_CHECK_FAILURE_REASON)
            return False
        if manufacturer_active:
            return True

        logger.info(
            "Discovery synchronization stopped for inactive manufacturer ID %s",
            manufacturer.pk,
        )
        summary.record_error(MANUFACTURER_INACTIVE_REASON)
        return False

    def _execute_claimed_workflow(
        self,
        manufacturer: Manufacturer,
        summary: DiscoverySyncSummary,
        *,
        add_cidrs: list[str] | None,
        add_fqdns: list[str] | None,
        scan_cidrs: bool,
        scan_fqdns: bool,
        max_hosts: int,
    ) -> None:
        """Run the vendor and persistence work for one active claimed manufacturer."""
        candidate_limit = clamp_candidate_limit(max_hosts)
        if not DiscoveryConfigurationService.add_entries(
            manufacturer,
            cidrs=add_cidrs,
            fqdns=add_fqdns,
        ):
            summary.record_error(CONFIG_ENTRIES_INCOMPLETE_REASON)
        plugin = get_manufacturer_plugin_instance(manufacturer)
        client = plugin.get_client()
        if not DiscoveryConfigurationService.persist_supported_models(
            manufacturer,
            getattr(client, "devices", None),
        ):
            summary.record_error(SUPPORTED_MODELS_INCOMPLETE_REASON)
        inventory_page = DiscoveryCandidateSourceService.collect_inventory_candidates(
            manufacturer,
            limit=candidate_limit,
        )
        if not inventory_page.sources_complete:
            summary.record_error(INVENTORY_SOURCES_INCOMPLETE_REASON)
        remaining_candidates = candidate_limit - len(inventory_page.candidates)
        scan_source_page = DiscoveryCandidateSourceService.configured_scan_sources(
            manufacturer,
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
            limit=remaining_candidates,
        )
        if not scan_source_page.sources_complete:
            summary.record_error(SCAN_SOURCES_INCOMPLETE_REASON)
        scanned_page = DiscoveryCandidateSourceService.collect_scanned_candidates(
            cidrs=scan_source_page.cidrs,
            fqdns=scan_source_page.fqdns,
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
            max_hosts=remaining_candidates,
            source_order=scan_source_page.source_order,
        )
        if (
            not scanned_page.sources_complete
            and SCAN_SOURCES_INCOMPLETE_REASON not in summary.errors
        ):
            summary.record_error(SCAN_SOURCES_INCOMPLETE_REASON)
        self.submit_candidates(
            manufacturer,
            missing_ips=inventory_page.candidates,
            scanned_ips=scanned_page.candidates,
            plugin=plugin,
            summary=summary,
        )
        DiscoveryQueueService.poll_and_persist(manufacturer, plugin, summary)

    def submit_candidates(
        self,
        manufacturer: Manufacturer,
        *,
        missing_ips: list[str],
        scanned_ips: list[str],
        plugin: ManufacturerPlugin,
        summary: DiscoverySyncSummary,
    ) -> None:
        """Submit inventory and scanned candidates through one deduplicated vendor batch."""
        unique_missing = list(dict.fromkeys(str(ip) for ip in missing_ips if ip))
        missing_set = set(unique_missing)
        unique_scanned = [
            ip
            for ip in dict.fromkeys(str(candidate) for candidate in scanned_ips if candidate)
            if ip not in missing_set
        ]
        submission = self.discovery_service.add_discovery_candidates(
            manufacturer,
            [*unique_missing, *unique_scanned],
            plugin=plugin,
            batch_size=DISCOVERY_SUBMISSION_BATCH_SIZE,
        )
        submitted = set(submission.submitted_ips)
        failed = set(submission.failed_ips)
        summary.missing_ips_submitted += sum(ip in submitted for ip in unique_missing)
        summary.scanned_ips_submitted += sum(ip in submitted for ip in unique_scanned)
        failed_missing_count = sum(ip in failed for ip in unique_missing)
        failed_scanned_count = sum(ip in failed for ip in unique_scanned)
        if failed_missing_count:
            summary.record_error(
                f"Failed to submit {failed_missing_count} missing discovery candidate"
                f"{'s' if failed_missing_count != 1 else ''}"
            )
        if failed_scanned_count:
            summary.record_error(
                f"Failed to submit {failed_scanned_count} scanned discovery candidate"
                f"{'s' if failed_scanned_count != 1 else ''}"
            )
        if submission.rejected_count:
            summary.record_error(
                f"Rejected {submission.rejected_count} invalid discovery candidate"
                f"{'s' if submission.rejected_count != 1 else ''}"
            )

    @staticmethod
    def broadcast_results(manufacturer: Manufacturer) -> None:
        """Broadcast the refreshed chassis projection without failing the sync."""
        try:
            limits = ManufacturerPollLimits.from_settings()
            DeviceSnapshotBroadcastService.broadcast(
                manufacturer=manufacturer,
                namespace="discovery",
                max_devices=limits.max_devices,
                chunk_size=limits.broadcast_chunk_size,
            )
        except Exception as exc:
            logger.exception(
                "Failed to broadcast discovery synchronization results",
                exc_info=sanitized_exception_info(exc),
            )
