"""Enhanced model managers with tenant support and optimizations.

Base classes for all models to support:
- Multi-tenancy (organization, campus, site)
- Optimization hints (select_related, prefetch_related)
- Common filtering patterns
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from micboard.multitenancy.models import Organization

_ModelT = TypeVar("_ModelT", bound=models.Model)


class TenantOptimizedQuerySet(models.QuerySet[_ModelT]):
    """Base QuerySet with tenant filtering and optimization methods.

    Extends the multitenancy TenantAwareQuerySet with common ORM optimizations.
    """

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

        if hasattr(self.model, "organization_id"):
            return self.filter(organization_id=org_id)
        if hasattr(self.model, "building"):
            return self.filter(building__organization_id=org_id)
        if hasattr(self.model, "location"):
            return self.filter(location__building__organization_id=org_id)
        if hasattr(self.model, "campus"):
            return self.filter(campus__organization_id=org_id)

        return self

    def for_campus(self, *, campus_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Campus (MSP mode)."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return self

        if campus_id is None:
            return self

        if hasattr(self.model, "campus_id"):
            return self.filter(campus_id=campus_id)
        if hasattr(self.model, "building"):
            return self.filter(building__campus_id=campus_id)
        if hasattr(self.model, "location"):
            return self.filter(location__building__campus_id=campus_id)

        return self

    def for_user(self, *, user: User) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter based on user permissions and tenant context.

        Respects MSP, multi-site, and single-site modes.
        """
        if user.is_superuser:
            if not getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True):
                # Even superuser limited to their orgs
                pass
            else:
                return self

        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            from micboard.multitenancy.models import OrganizationMembership

            user_orgs = OrganizationMembership.objects.filter(
                user=user, is_active=True
            ).values_list("organization_id", flat=True)

            if not user_orgs:
                return self.none()

            return self.for_organization(organization=list(user_orgs)[0])

        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self.for_site()

        # Single-site: use monitoring group filtering if available
        if hasattr(self.model, "location"):
            if hasattr(user, "monitoring_groups"):
                user_locations = (
                    user.monitoring_groups.filter(is_active=True)
                    .values_list("monitoringgrouplocation__location", flat=True)
                    .distinct()
                )

                if not user_locations.exists():
                    return self.none()

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

    def for_user(self, *, user: User) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().for_user(user=user)

    def with_manufacturer(self) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().with_manufacturer()

    def with_location(self) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().with_location()

    def with_receiver(self) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().with_receiver()

    def recently_seen(self, *, minutes: int = 30) -> TenantOptimizedQuerySet[_ModelT]:
        return self.get_queryset().recently_seen(minutes=minutes)
