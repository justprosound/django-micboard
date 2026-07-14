"""Service for triggering async discovery scans for manufacturers."""

import logging

from django.dispatch import Signal

from micboard.utils.dependencies import huey_is_configured

logger = logging.getLogger(__name__)
discovery_requested = Signal()


def trigger_discovery(manufacturer_id: int | None) -> None:
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
        scan_cidrs=True,
        scan_fqdns=True,
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
                exc_info=(type(response), response, response.__traceback__),
            )
