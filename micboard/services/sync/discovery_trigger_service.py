"""Service for triggering async discovery scans for manufacturers."""

import logging

from micboard.utils.dependencies import HAS_DJANGO_Q

logger = logging.getLogger(__name__)


def trigger_discovery(manufacturer_id: int | None) -> None:
    """Trigger async discovery scan for a manufacturer."""
    if not HAS_DJANGO_Q:
        logger.debug("django-q not available, skipping discovery trigger")
        return
    if not manufacturer_id:
        logger.warning("No manufacturer_id available for discovery trigger")
        return
    from micboard.services.sync.discovery_service import DiscoveryService

    DiscoveryService.trigger_manufacturer_discovery(
        manufacturer_id, scan_cidrs=True, scan_fqdns=True
    )
