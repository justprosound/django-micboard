"""Tenant-aware filtering helpers for service layer querysets."""

from __future__ import annotations

from django.db.models import Model, QuerySet

from micboard.services.settings.settings_service import settings


def apply_tenant_filters[ModelT: Model](
    qs: QuerySet[ModelT],
    *,
    organization_id: int | None = None,
    campus_id: int | None = None,
    site_id: int | None = None,
    building_path: str = "location__building",
) -> QuerySet[ModelT]:
    """Apply tenant/site filters to a queryset using configured mode.

    Args:
        qs: QuerySet to filter.
        organization_id: Organization ID (MSP mode).
        campus_id: Campus ID (MSP mode).
        site_id: Site ID (multi-site mode).
        building_path: ORM path to building relation.

    Returns:
        Filtered QuerySet according to tenant configuration.
    """
    if settings.msp_enabled:
        if organization_id:
            qs = qs.filter(**{f"{building_path}__organization_id": organization_id})
        if campus_id:
            qs = qs.filter(**{f"{building_path}__campus_id": campus_id})
        return qs

    if settings.multi_site_mode:
        if site_id:
            qs = qs.filter(**{f"{building_path}__site_id": site_id})
        return qs

    return qs
