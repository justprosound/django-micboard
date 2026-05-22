"""Service functions for Building model business logic.

Provides regulatory domain auto-assignment and persistence logic,
separated from the model layer per ADR-002.
"""

from __future__ import annotations


def save_building(building, *args, **kwargs) -> None:
    """Auto-assign regulatory domain based on country if not set, then save."""
    from django.db import OperationalError, ProgrammingError

    from micboard.models.rf_coordination import RegulatoryDomain

    if building.country and not building.regulatory_domain:
        try:
            domain = RegulatoryDomain.objects.filter(country_code=building.country.upper()).first()
            if domain:
                building.regulatory_domain = domain
        except (ProgrammingError, OperationalError):
            pass

    from micboard.models.locations.structure import Building as _Building

    super(_Building, building).save(*args, **kwargs)
