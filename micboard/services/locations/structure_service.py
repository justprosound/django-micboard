"""Service functions for Building model business logic.

Provides regulatory domain auto-assignment and persistence logic,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from micboard.models.locations.structure import Building


def prepare_building(building: Building) -> None:
    """Auto-assign a building's regulatory domain from its country."""
    from django.db import OperationalError, ProgrammingError

    from micboard.models.rf_coordination.compliance import RegulatoryDomain

    if building.country and not building.regulatory_domain:
        try:
            domain = RegulatoryDomain.objects.filter(country_code=building.country.upper()).first()
            if domain:
                building.regulatory_domain = domain
        except (ProgrammingError, OperationalError) as exc:
            logger.exception(
                "Could not resolve the regulatory domain for building country %s",
                building.country,
                exc_info=sanitized_exception_info(exc),
            )
