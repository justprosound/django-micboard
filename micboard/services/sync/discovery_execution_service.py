"""Service-layer execution for background discovery entry points."""

from __future__ import annotations

import logging
from itertools import islice

from django.core.cache import cache

from micboard.discovery.limits import (
    DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    MAX_DISCOVERY_CANDIDATES,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.sync.discovery_claim_service import DiscoverySyncClaimService
from micboard.services.sync.discovery_dtos import (
    DiscoveryReconciliationResult,
    DiscoverySyncSummary,
)
from micboard.services.sync.discovery_service import DiscoveryService
from micboard.services.sync.discovery_utils import get_manufacturer_plugin_instance
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

CLAIM_FAILURE_REASON = "discovery_claim_failed"
RECONCILIATION_FAILURE_REASON = "vendor_reconciliation_failed"
FINALIZATION_FAILURE_REASON = "discovery_finalization_failed"
MANUFACTURER_INACTIVE_REASON = "manufacturer_inactive"
MANUFACTURER_STATUS_CHECK_FAILURE_REASON = "manufacturer_status_check_failed"


class DiscoveryExecutionService:
    """Contain recoverable work launched by Huey discovery tasks."""

    @staticmethod
    def run_manufacturer(
        manufacturer_id: int,
        *,
        scan_cidrs: bool,
        scan_fqdns: bool,
    ) -> DiscoveryReconciliationResult:
        """Run vendor discovery reconciliation for one manufacturer."""
        summary = DiscoverySyncSummary(manufacturer=manufacturer_id)
        claim_service = DiscoverySyncClaimService()
        try:
            claim = claim_service.claim(manufacturer_id)
        except Manufacturer.DoesNotExist:
            logger.warning("Manufacturer with ID %s not found for discovery.", manufacturer_id)
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason="manufacturer_not_found",
            )
        except Exception as exc:
            logger.exception(
                "Error claiming discovery for manufacturer ID %s",
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason=CLAIM_FAILURE_REASON,
            )

        if claim is None:
            logger.info(
                "Discovery reconciliation already running for manufacturer ID %s",
                manufacturer_id,
            )
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="busy",
                reason="manufacturer_reconciliation_busy",
            )

        manufacturer, job = claim
        if DiscoveryExecutionService._record_current_activation_state(
            manufacturer_id,
            summary,
        ):
            try:
                reconciliation = DiscoveryService().run_manufacturer_discovery(
                    manufacturer,
                    scan_cidrs=scan_cidrs,
                    scan_fqdns=scan_fqdns,
                    max_hosts=DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
                )
                if not reconciliation.success:
                    summary.record_error(RECONCILIATION_FAILURE_REASON)
            except Exception as exc:
                logger.exception(
                    "Error running discovery for manufacturer ID %s",
                    manufacturer_id,
                    exc_info=sanitized_exception_info(exc),
                )
                summary.record_error(RECONCILIATION_FAILURE_REASON)

        try:
            finalized = claim_service.finalize(job, summary)
        except Exception as exc:
            logger.exception(
                "Error finalizing discovery for manufacturer ID %s",
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason=FINALIZATION_FAILURE_REASON,
            )
        if not finalized:
            logger.warning("Discovery claim expired for manufacturer ID %s", manufacturer_id)
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason="discovery_claim_expired",
            )

        logger.info(
            "Discovery reconciliation finished for %s (CIDRs: %s, FQDNs: %s)",
            manufacturer.code,
            scan_cidrs,
            scan_fqdns,
        )
        if summary.errors:
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason=summary.errors[0],
            )
        return DiscoveryReconciliationResult(
            manufacturer=manufacturer_id,
            status="success",
        )

    @staticmethod
    def _record_current_activation_state(
        manufacturer_id: int,
        summary: DiscoverySyncSummary,
    ) -> bool:
        """Fail closed and record why current activation cannot permit discovery."""
        failure_reason = DiscoveryExecutionService._activation_failure_reason(
            manufacturer_id,
            operation="discovery reconciliation",
        )
        if failure_reason is None:
            return True
        summary.record_error(failure_reason)
        return False

    @staticmethod
    def _activation_failure_reason(
        manufacturer_id: int,
        *,
        operation: str,
    ) -> str | None:
        """Return a fail-closed reason when fresh activation cannot permit vendor work."""
        try:
            manufacturer_active = ManufacturerActivationService.is_active(manufacturer_id)
        except Exception as exc:
            logger.exception(
                "Error revalidating manufacturer ID %s before %s",
                manufacturer_id,
                operation,
                exc_info=sanitized_exception_info(exc),
            )
            return MANUFACTURER_STATUS_CHECK_FAILURE_REASON
        if manufacturer_active:
            return None

        logger.info(
            "%s stopped for inactive manufacturer ID %s",
            operation.capitalize(),
            manufacturer_id,
        )
        return MANUFACTURER_INACTIVE_REASON

    @classmethod
    def cache_all_candidates(cls, *, scan_cidrs: bool, scan_fqdns: bool) -> None:
        """Refresh and cache each manufacturer's vendor discovery candidates."""
        logger.info(
            "Caching all discovery candidates (CIDRs: %s, FQDNs: %s)",
            scan_cidrs,
            scan_fqdns,
        )
        manufacturers = list(Manufacturer.objects.order_by("pk")[: MAX_DISCOVERY_CANDIDATES + 1])
        if len(manufacturers) > MAX_DISCOVERY_CANDIDATES:
            logger.warning("Manufacturer discovery cache refresh reached the hard limit")
        for manufacturer in manufacturers[:MAX_DISCOVERY_CANDIDATES]:
            try:
                outcome = cls.run_manufacturer(
                    manufacturer.pk,
                    scan_cidrs=scan_cidrs,
                    scan_fqdns=scan_fqdns,
                )
                if outcome.status != "success":
                    logger.info(
                        "Skipping discovery cache refresh for %s after %s outcome",
                        manufacturer.code,
                        outcome.status,
                    )
                    continue
                activation_failure = cls._activation_failure_reason(
                    manufacturer.pk,
                    operation="discovery cache refresh",
                )
                if activation_failure is not None:
                    logger.info(
                        "Skipping discovery cache refresh for %s after %s",
                        manufacturer.code,
                        activation_failure,
                    )
                    continue
                remote_ips = (
                    get_manufacturer_plugin_instance(manufacturer).get_discovery_ips() or []
                )
                raw_ips = list(islice(iter(remote_ips), MAX_DISCOVERY_CANDIDATES + 1))
                bounded_ips, rejected_count = DiscoveryService.canonicalize_ip_addresses(
                    raw_ips[:MAX_DISCOVERY_CANDIDATES]
                )
                if len(raw_ips) > MAX_DISCOVERY_CANDIDATES or rejected_count:
                    logger.warning(
                        "Skipping incomplete discovery cache refresh for %s",
                        manufacturer.code,
                    )
                    continue
                cache_key = (
                    f"discovery_candidates_{manufacturer.code}_{int(scan_cidrs)}_{int(scan_fqdns)}"
                )
                cache.set(cache_key, {manufacturer.code: {"ips": bounded_ips}}, timeout=300)
                logger.info("Cached %d candidates for %s", len(bounded_ips), manufacturer.code)
            except Exception as exc:
                logger.exception(
                    "Failed to compute discovery candidates for %s",
                    manufacturer.code,
                    exc_info=sanitized_exception_info(exc),
                )
