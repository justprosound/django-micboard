"""Native Huey entry points for discovery workflows."""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.dispatch import receiver

from huey.exceptions import RetryTask

from micboard.discovery.limits import DEFAULT_DISCOVERY_CANDIDATE_LIMIT
from micboard.services.sync.discovery_execution_service import DiscoveryExecutionService
from micboard.services.sync.discovery_sync_service import DiscoverySyncService
from micboard.services.sync.discovery_trigger_service import (
    claim_discovery_dispatch,
    discovery_requested,
    release_discovery_dispatch,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

BUSY_RETRY_DELAY_SECONDS = 15
BUSY_RETRY_COALESCE_SECONDS = 10


def run_manufacturer_discovery_task(
    manufacturer_id: int,
    scan_cidrs: bool,
    scan_fqdns: bool,
) -> dict[str, Any]:
    """Run discovery reconciliation for one manufacturer."""
    outcome = DiscoveryExecutionService.run_manufacturer(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    if outcome.status == "busy":
        retry_key = f"micboard:discovery-retry:{manufacturer_id}"
        if cache.add(retry_key, True, timeout=BUSY_RETRY_COALESCE_SECONDS):
            raise RetryTask(delay=BUSY_RETRY_DELAY_SECONDS)
    return outcome.model_dump()


def dispatch_manufacturer_discovery(
    manufacturer_id: int,
    *,
    scan_cidrs: bool = True,
    scan_fqdns: bool = True,
) -> None:
    """Enqueue discovery without blocking request paths when Huey is disabled."""
    from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

    if not manufacturer_id:
        logger.warning("No manufacturer_id available for discovery dispatch")
        return

    if not huey_is_configured():
        logger.debug("Native Huey is unavailable or unconfigured; skipping discovery dispatch")
        return

    if not claim_discovery_dispatch(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    ):
        return

    try:
        enqueue_huey_task(
            run_manufacturer_discovery_task,
            manufacturer_id,
            scan_cidrs,
            scan_fqdns,
        )
    except Exception as exc:
        release_discovery_dispatch(
            manufacturer_id,
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
        )
        logger.exception(
            "Failed to enqueue discovery task for manufacturer %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )


@receiver(discovery_requested, dispatch_uid="micboard.dispatch_manufacturer_discovery")
def _dispatch_discovery_request(
    sender: object,
    *,
    manufacturer_id: int,
    scan_cidrs: bool,
    scan_fqdns: bool,
    **kwargs: Any,
) -> None:
    """Bridge service-layer discovery events to the task dispatcher."""
    del sender, kwargs
    dispatch_manufacturer_discovery(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )


def cache_all_discovery_candidates(
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
) -> None:
    """Refresh and cache discovery candidate IPs for all manufacturers."""
    DiscoveryExecutionService.cache_all_candidates(
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )


def run_discovery_sync_task(
    manufacturer_id: int,
    add_cidrs: list[str] | None = None,
    add_fqdns: list[str] | None = None,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = DEFAULT_DISCOVERY_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    """Synchronize vendor discovery state and return a stable result mapping."""
    return DiscoverySyncService().run(
        manufacturer_id,
        add_cidrs=add_cidrs,
        add_fqdns=add_fqdns,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
        max_hosts=max_hosts,
    )
