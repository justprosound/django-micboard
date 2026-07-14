"""Service for triggering async discovery scans for manufacturers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.dispatch import Signal

from micboard.utils.dependencies import huey_is_configured
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)
discovery_requested = Signal()
DISCOVERY_DISPATCH_COALESCE_SECONDS = 5

type DiscoveryScheduleKey = tuple[int, bool, bool, str]

_pending_discovery_schedules: ContextVar[dict[DiscoveryScheduleKey, None] | None] = ContextVar(
    "micboard_pending_discovery_schedules",
    default=None,
)


def trigger_discovery(
    manufacturer_id: int | None,
    *,
    scan_cidrs: bool = True,
    scan_fqdns: bool = True,
) -> None:
    """Publish an asynchronous discovery request to task-layer subscribers."""
    if not manufacturer_id:
        logger.warning("No manufacturer_id available for discovery trigger")
        return
    if not huey_is_configured():
        logger.debug("Native Huey is unavailable or unconfigured; skipping discovery trigger")
        return

    responses = discovery_requested.send_robust(
        sender=trigger_discovery,
        manufacturer_id=manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    if not responses:
        logger.warning("No task-layer discovery dispatcher is registered")
        return
    for receiver, response in responses:
        if isinstance(response, Exception):
            logger.error(
                "Discovery dispatcher %r failed for manufacturer %s",
                receiver,
                manufacturer_id,
                exc_info=sanitized_exception_info(response),
            )


def schedule_discovery_on_commit(
    *,
    manufacturer_id: int,
    scan_cidrs: bool,
    scan_fqdns: bool,
    using: str,
) -> None:
    """Schedule one deduplicated manufacturer reconciliation after commit."""
    pending = _pending_discovery_schedules.get()
    if pending is not None:
        pending[(manufacturer_id, scan_cidrs, scan_fqdns, using)] = None
        return

    _register_discovery_on_commit(
        manufacturer_id=manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
        using=using,
    )


def _register_discovery_on_commit(
    *,
    manufacturer_id: int,
    scan_cidrs: bool,
    scan_fqdns: bool,
    using: str,
) -> None:
    """Register one transaction-bound discovery callback."""
    connection = transaction.get_connection(using)
    discovery_key = (manufacturer_id, scan_cidrs, scan_fqdns)
    if any(
        getattr(callback, "_micboard_discovery_key", None) == discovery_key
        for _callback_savepoints, callback, _robust in connection.run_on_commit
    ):
        return

    callback = partial(
        _dispatch_scheduled_discovery,
        manufacturer_id=manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    callback.__dict__["_micboard_discovery_key"] = discovery_key
    transaction.on_commit(callback, using=using, robust=True)


@contextmanager
def coalesce_discovery_scheduling() -> Iterator[None]:
    """Defer repeated lifecycle schedules and register each unique request once."""
    existing = _pending_discovery_schedules.get()
    if existing is not None:
        yield
        return

    pending: dict[DiscoveryScheduleKey, None] = {}
    token = _pending_discovery_schedules.set(pending)
    try:
        yield
    finally:
        _pending_discovery_schedules.reset(token)
        for manufacturer_id, scan_cidrs, scan_fqdns, using in pending:
            _register_discovery_on_commit(
                manufacturer_id=manufacturer_id,
                scan_cidrs=scan_cidrs,
                scan_fqdns=scan_fqdns,
                using=using,
            )


def _discovery_dispatch_cache_key(
    manufacturer_id: int,
    *,
    scan_cidrs: bool,
    scan_fqdns: bool,
) -> str:
    """Return a bounded cache key for one queue-dispatch shape."""
    return f"micboard:discovery-dispatch:{manufacturer_id}:{int(scan_cidrs)}:{int(scan_fqdns)}"


def claim_discovery_dispatch(
    manufacturer_id: int,
    *,
    scan_cidrs: bool,
    scan_fqdns: bool,
) -> bool:
    """Claim a short process-shared window, failing open when cache is unavailable."""
    cache_key = _discovery_dispatch_cache_key(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    try:
        claimed = bool(cache.add(cache_key, True, timeout=DISCOVERY_DISPATCH_COALESCE_SECONDS))
        if claimed:
            return True
        return cache.get(cache_key) is None
    except Exception as exc:
        logger.exception(
            "Discovery dispatch cache unavailable; proceeding without coalescing",
            exc_info=sanitized_exception_info(exc),
        )
        return True


def release_discovery_dispatch(
    manufacturer_id: int,
    *,
    scan_cidrs: bool,
    scan_fqdns: bool,
) -> None:
    """Release a queue claim after enqueue failure so retries are not suppressed."""
    cache_key = _discovery_dispatch_cache_key(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    try:
        cache.delete(cache_key)
    except Exception as exc:
        logger.exception(
            "Discovery dispatch cache claim could not be released",
            exc_info=sanitized_exception_info(exc),
        )


def _dispatch_scheduled_discovery(
    *, manufacturer_id: int, scan_cidrs: bool, scan_fqdns: bool
) -> None:
    """Dispatch a committed lifecycle request outside test environments."""
    if getattr(settings, "TESTING", False):
        return
    trigger_discovery(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
