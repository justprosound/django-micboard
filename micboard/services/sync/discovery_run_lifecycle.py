"""One claimed-run lifecycle shared by discovery execution and discovery synchronization."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.sync.discovery_claim_service import DiscoverySyncClaimService
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

CLAIM_FAILURE_REASON = "discovery_claim_failed"
FINALIZATION_FAILURE_REASON = "discovery_finalization_failed"
MANUFACTURER_INACTIVE_REASON = "manufacturer_inactive"
MANUFACTURER_STATUS_CHECK_FAILURE_REASON = "manufacturer_status_check_failed"

ClaimedWork = Callable[[Manufacturer, DiscoverySyncSummary], None]


class ClaimedRunStatus(StrEnum):
    """How one claimed discovery run ended, before a flavour maps it to its result shape."""

    NOT_FOUND = "not_found"
    CLAIM_FAILED = "claim_failed"
    BUSY = "busy"
    FINALIZE_FAILED = "finalize_failed"
    CLAIM_EXPIRED = "claim_expired"
    FINALIZED = "finalized"


@dataclass(frozen=True)
class ClaimedRunOutcome:
    """Lifecycle outcome handed to a flavour's result mapping."""

    status: ClaimedRunStatus
    summary: DiscoverySyncSummary
    manufacturer: Manufacturer | None = None
    work_completed: bool = False


def activation_failure_reason(manufacturer_id: int, *, operation: str) -> str | None:
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


class DiscoveryClaimedRun:
    """Claim a manufacturer, run caller-supplied work, and finalize the claim."""

    def __init__(self, claim_service: DiscoverySyncClaimService | None = None) -> None:
        """Create the lifecycle with an optional claim service."""
        self.claim_service = (
            claim_service if claim_service is not None else DiscoverySyncClaimService()
        )

    def run(
        self,
        manufacturer_id: int,
        *,
        operation: str,
        work: ClaimedWork,
        work_failure_reason: str,
    ) -> ClaimedRunOutcome:
        """Run ``work`` under the claim; the caller maps the outcome to its own result.

        ``work`` records its own incomplete-source errors on the summary and raises on
        unrecoverable failure, which the lifecycle contains as ``work_failure_reason``.
        """
        summary = DiscoverySyncSummary(manufacturer=manufacturer_id)
        try:
            claim = self.claim_service.claim(manufacturer_id)
        except Manufacturer.DoesNotExist:
            logger.warning("Manufacturer with ID %s not found for %s", manufacturer_id, operation)
            return ClaimedRunOutcome(ClaimedRunStatus.NOT_FOUND, summary)
        except Exception as exc:
            logger.exception(
                "Error claiming %s for manufacturer ID %s",
                operation,
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            return ClaimedRunOutcome(ClaimedRunStatus.CLAIM_FAILED, summary)
        if claim is None:
            logger.info("%s already running for manufacturer ID %s", operation, manufacturer_id)
            return ClaimedRunOutcome(ClaimedRunStatus.BUSY, summary)

        manufacturer, job = claim
        work_completed = False
        inactive_reason = activation_failure_reason(manufacturer_id, operation=operation)
        if inactive_reason is not None:
            summary.record_error(inactive_reason)
        else:
            try:
                work(manufacturer, summary)
                work_completed = True
            except Exception as exc:
                logger.exception(
                    "Error running %s for manufacturer ID %s",
                    operation,
                    manufacturer_id,
                    exc_info=sanitized_exception_info(exc),
                )
                summary.record_error(work_failure_reason)

        try:
            finalized = self.claim_service.finalize(job, summary)
        except Exception as exc:
            logger.exception(
                "Error finalizing %s for manufacturer ID %s",
                operation,
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )
            return ClaimedRunOutcome(
                ClaimedRunStatus.FINALIZE_FAILED, summary, manufacturer, work_completed
            )
        if not finalized:
            logger.warning("%s claim expired for manufacturer ID %s", operation, manufacturer_id)
            return ClaimedRunOutcome(
                ClaimedRunStatus.CLAIM_EXPIRED, summary, manufacturer, work_completed
            )
        return ClaimedRunOutcome(ClaimedRunStatus.FINALIZED, summary, manufacturer, work_completed)
