"""Service-layer execution for background discovery entry points."""

import logging
from itertools import islice

from django.core.cache import cache

from micboard.discovery.limits import (
    DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
    MAX_DISCOVERY_CANDIDATES,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.common.base.plugin import build_manufacturer_plugin
from micboard.services.sync.discovery_dtos import (
    DiscoveryReconciliationResult,
    DiscoverySyncSummary,
)
from micboard.services.sync.discovery_run_lifecycle import (
    CLAIM_FAILURE_REASON,
    FINALIZATION_FAILURE_REASON,
    ClaimedRunOutcome,
    ClaimedRunStatus,
    DiscoveryClaimedRun,
    activation_failure_reason,
)
from micboard.services.sync.discovery_service import DiscoveryService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

RECONCILIATION_FAILURE_REASON = "vendor_reconciliation_failed"
RECONCILIATION_OPERATION = "discovery reconciliation"

_FAILED_REASONS = {
    ClaimedRunStatus.NOT_FOUND: "manufacturer_not_found",
    ClaimedRunStatus.CLAIM_FAILED: CLAIM_FAILURE_REASON,
    ClaimedRunStatus.FINALIZE_FAILED: FINALIZATION_FAILURE_REASON,
    ClaimedRunStatus.CLAIM_EXPIRED: "discovery_claim_expired",
}


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

        def reconcile(manufacturer: Manufacturer, summary: DiscoverySyncSummary) -> None:
            reconciliation = DiscoveryService().run_manufacturer_discovery(
                manufacturer,
                scan_cidrs=scan_cidrs,
                scan_fqdns=scan_fqdns,
                max_hosts=DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
            )
            if not reconciliation.success:
                summary.record_error(RECONCILIATION_FAILURE_REASON)

        outcome = DiscoveryClaimedRun().run(
            manufacturer_id,
            operation=RECONCILIATION_OPERATION,
            work=reconcile,
            work_failure_reason=RECONCILIATION_FAILURE_REASON,
        )
        return DiscoveryExecutionService._to_result(manufacturer_id, outcome)

    @staticmethod
    def _to_result(
        manufacturer_id: int,
        outcome: ClaimedRunOutcome,
    ) -> DiscoveryReconciliationResult:
        """Map a lifecycle outcome to the stable reconciliation result."""
        if outcome.status is ClaimedRunStatus.BUSY:
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="busy",
                reason="manufacturer_reconciliation_busy",
            )
        if outcome.status in _FAILED_REASONS:
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason=_FAILED_REASONS[outcome.status],
            )
        if outcome.summary.errors:
            return DiscoveryReconciliationResult(
                manufacturer=manufacturer_id,
                status="failed",
                reason=outcome.summary.errors[0],
            )
        return DiscoveryReconciliationResult(manufacturer=manufacturer_id, status="success")

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
                failure = activation_failure_reason(
                    manufacturer.pk,
                    operation="discovery cache refresh",
                )
                if failure is not None:
                    logger.info(
                        "Skipping discovery cache refresh for %s after %s",
                        manufacturer.code,
                        failure,
                    )
                    continue
                remote_ips = build_manufacturer_plugin(manufacturer).get_discovery_ips() or []
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
