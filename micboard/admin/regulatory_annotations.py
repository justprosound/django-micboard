"""Query projections for regulatory status admin columns."""

from __future__ import annotations

from typing import Any

from django.db.models import CharField, F, FloatField, OuterRef, Subquery
from django.db.models.functions import Coalesce, Upper

from micboard.models.rf_coordination.compliance import RegulatoryDomain
from micboard.services.hardware.dtos import RegulatoryDomainDTO


def with_regulatory_domain(queryset: Any, *, building_path: str) -> Any:
    """Annotate an explicit or country-fallback regulatory domain in one query."""
    country_path = f"{building_path}__country"
    explicit_path = f"{building_path}__regulatory_domain"
    fallback = RegulatoryDomain.objects.filter(
        country_code=Upper(OuterRef(country_path)),
    ).order_by("pk")
    return queryset.annotate(
        _regulatory_domain_code=Coalesce(
            F(f"{explicit_path}__code"),
            Subquery(fallback.values("code")[:1]),
            output_field=CharField(),
        ),
        _regulatory_min_mhz=Coalesce(
            F(f"{explicit_path}__min_frequency_mhz"),
            Subquery(fallback.values("min_frequency_mhz")[:1]),
            output_field=FloatField(),
        ),
        _regulatory_max_mhz=Coalesce(
            F(f"{explicit_path}__max_frequency_mhz"),
            Subquery(fallback.values("max_frequency_mhz")[:1]),
            output_field=FloatField(),
        ),
    )


def regulatory_domain_from_annotations(obj: Any) -> RegulatoryDomainDTO | None:
    """Map regulatory annotations to the typed service projection."""
    code = getattr(obj, "_regulatory_domain_code", None)
    minimum = getattr(obj, "_regulatory_min_mhz", None)
    maximum = getattr(obj, "_regulatory_max_mhz", None)
    if code is None or minimum is None or maximum is None:
        return None
    return RegulatoryDomainDTO(
        code=code,
        min_frequency_mhz=minimum,
        max_frequency_mhz=maximum,
    )
