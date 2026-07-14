"""Enhanced model managers with tenant support and optimizations.

Base classes for all models to support:
- Multi-tenancy (organization, campus, site)
- Optimization hints (select_related, prefetch_related)
- Common filtering patterns
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TypeVar

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Q

if TYPE_CHECKING:
    from micboard.multitenancy.models import Organization

_ModelT = TypeVar("_ModelT", bound=models.Model)


class TenantOptimizedQuerySet(models.QuerySet[_ModelT]):
    """Base QuerySet with tenant filtering and optimization methods.

    Provides the canonical tenant filters and common ORM optimizations.
    """

    def _tenant_lookups(self) -> tuple[str, str | None] | None:
        """Return organization and campus lookups for the queryset model."""
        model_label = getattr(getattr(self.model, "_meta", None), "label_lower", "")
        direct_tenant_lookups: dict[str, tuple[str, str | None]] = {
            "micboard_multitenancy.organization": ("pk", None),
            "micboard_multitenancy.campus": ("organization_id", "pk"),
        }
        if model_label in direct_tenant_lookups:
            return direct_tenant_lookups[model_label]
        if hasattr(self.model, "organization_id"):
            campus_lookup = "campus_id" if hasattr(self.model, "campus_id") else None
            return "organization_id", campus_lookup
        if hasattr(self.model, "building"):
            return "building__organization_id", "building__campus_id"
        if hasattr(self.model, "location"):
            return "location__building__organization_id", "location__building__campus_id"
        if hasattr(self.model, "base_chassis"):
            prefix = "base_chassis__location__building"
            return f"{prefix}__organization_id", f"{prefix}__campus_id"
        if hasattr(self.model, "chassis"):
            prefix = "chassis__location__building"
            return f"{prefix}__organization_id", f"{prefix}__campus_id"
        if hasattr(self.model, "wireless_unit"):
            prefix = "wireless_unit__base_chassis__location__building"
            return f"{prefix}__organization_id", f"{prefix}__campus_id"
        if hasattr(self.model, "assignments"):
            prefix = "assignments__wireless_unit__base_chassis__location__building"
            return f"{prefix}__organization_id", f"{prefix}__campus_id"
        if hasattr(self.model, "campus"):
            return "campus__organization_id", "campus_id"
        return None

    def _campus_lookup(self) -> str | None:
        """Return the campus lookup for the queryset model, when available."""
        if hasattr(self.model, "campus_id"):
            return "campus_id"
        lookups = TenantOptimizedQuerySet._tenant_lookups(self)
        return lookups[1] if lookups is not None else None

    def for_site(self, *, site_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Django Site (multi-site mode)."""
        if not getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self

        site_id = site_id or getattr(settings, "SITE_ID", 1)

        if hasattr(self.model, "site_id"):
            return self.filter(site_id=site_id)
        if hasattr(self.model, "building"):
            return self.filter(building__site_id=site_id)
        if hasattr(self.model, "location"):
            return self.filter(location__building__site_id=site_id)

        return self

    def for_organization(
        self, *, organization: Organization | int | None = None
    ) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Organization (MSP mode)."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return self

        if organization is None:
            return self

        org_id = organization.id if hasattr(organization, "id") else organization

        lookups = TenantOptimizedQuerySet._tenant_lookups(self)
        if lookups is None:
            return self.none()
        organization_lookup, _ = lookups
        return self.filter(**{organization_lookup: org_id})

    def for_campus(self, *, campus_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Campus (MSP mode)."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return self

        if campus_id is None:
            return self

        campus_lookup = TenantOptimizedQuerySet._campus_lookup(self)
        if campus_lookup is None:
            return self.none()
        return self.filter(**{campus_lookup: campus_id})

    def _for_memberships(
        self,
        memberships: Sequence[tuple[int, int | None]],
    ) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter through every active organization/campus membership."""
        tenant_filter: Q | None = None
        lookups = TenantOptimizedQuerySet._tenant_lookups(self)
        if lookups is None:
            return self.none()
        organization_lookup, campus_lookup = lookups

        for organization_id, campus_id in memberships:
            scope = Q(**{organization_lookup: organization_id})
            if campus_id is not None:
                if campus_lookup is None:
                    if organization_lookup != "pk":
                        continue
                else:
                    scope &= Q(**{campus_lookup: campus_id})

            tenant_filter = scope if tenant_filter is None else tenant_filter | scope

        if tenant_filter is None:
            return self.none()
        return self.filter(tenant_filter).distinct()

    def for_user(self, *, user: Any) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter based on user permissions and tenant context.

        Respects MSP, multi-site, and single-site modes.
        """
        if not getattr(user, "is_authenticated", True):
            return self.none()

        if user.is_superuser:
            if not getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True):
                # Even superuser limited to their orgs
                pass
            else:
                return self

        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            if not apps.is_installed("micboard.multitenancy"):
                return self.none()

            from micboard.multitenancy.models import OrganizationMembership

            memberships = list(
                OrganizationMembership._default_manager.filter(
                    user=user, is_active=True
                ).values_list("organization_id", "campus_id")
            )

            if not memberships:
                return self.none()

            return self._for_memberships(memberships)

        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self.for_site()

        # Single-site: use monitoring group filtering if available
        if hasattr(self.model, "location") and hasattr(user, "monitoring_groups"):
            from micboard.services.monitoring.monitoring_access import MonitoringService

            user_locations = MonitoringService.get_accessible_locations(user)
            return self.filter(location__in=user_locations)

        return self

    def with_manufacturer(self) -> TenantOptimizedQuerySet[_ModelT]:
        """Optimize: select_related manufacturer."""
        if hasattr(self.model, "manufacturer"):
            return self.select_related("manufacturer")
        return self

    def with_location(self) -> TenantOptimizedQuerySet[_ModelT]:
        """Optimize: select_related location and building."""
        if hasattr(self.model, "location"):
            return self.select_related("location", "location__building")
        return self

    def with_chassis(self) -> TenantOptimizedQuerySet[_ModelT]:
        """Optimize: select_related chassis."""
        if hasattr(self.model, "chassis"):
            return self.select_related("chassis", "chassis__manufacturer")
        return self

    def recently_seen(self, *, minutes: int = 30) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter objects seen within N minutes."""
        from datetime import timedelta

        from django.utils import timezone

        if not hasattr(self.model, "last_seen"):
            return self

        threshold = timezone.now() - timedelta(minutes=minutes)
        return self.filter(last_seen__gte=threshold)


class TenantOptimizedManager(models.Manager[_ModelT]):
    """Base manager with tenant filtering and optimization methods."""

    def get_queryset(self) -> TenantOptimizedQuerySet[_ModelT]:
        return TenantOptimizedQuerySet(self.model, using=self._db)

    def for_site(self, *, site_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().for_site(site_id=site_id)

    def for_organization(
        self, *, organization: Organization | int | None = None
    ) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().for_organization(organization=organization)

    def for_campus(self, *, campus_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().for_campus(campus_id=campus_id)

    def for_user(self, *, user: Any) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().for_user(user=user)

    def with_manufacturer(self) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().with_manufacturer()

    def with_location(self) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().with_location()

    def recently_seen(self, *, minutes: int = 30) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().recently_seen(minutes=minutes)
