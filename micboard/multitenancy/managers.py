"""Tenant-aware model managers for optional site/organization filtering.

These managers provide consistent filtering across single-site, multi-site,
and MSP deployments. They gracefully degrade when features are disabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from micboard.multitenancy.models import Organization


class TenantAwareQuerySet(models.QuerySet):
    """QuerySet that automatically filters by site/organization.

    Falls back to standard QuerySet behavior if multi-site mode disabled.
    """

    def for_site(self, *, site_id: int | None = None):
        """Filter by Django Site.

        Args:
            site_id: Optional site ID (defaults to settings.SITE_ID)

        Returns:
            Filtered queryset (or unfiltered if multi-site disabled)
        """
        if not getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self  # No-op in single-site mode

        site_id = site_id or getattr(settings, "SITE_ID", 1)

        # Check if model has direct site FK
        if hasattr(self.model, "site_id"):
            return self.filter(site_id=site_id)

        # Check if accessible via building
        if hasattr(self.model, "building"):
            return self.filter(building__site_id=site_id)

        # Check if accessible via location -> building
        if hasattr(self.model, "location"):
            return self.filter(location__building__site_id=site_id)

        return self

    def for_organization(self, *, organization: Organization | int | None = None):
        """Filter by Organization (MSP mode only).

        Args:
            organization: Organization instance or ID

        Returns:
            Filtered queryset (or unfiltered if MSP disabled)
        """
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return self  # No-op if MSP disabled

        if organization is None:
            return self

        org_id = organization.id if hasattr(organization, "id") else organization

        # Check if model has direct organization FK
        if hasattr(self.model, "organization_id"):
            return self.filter(organization_id=org_id)

        # Check if accessible via building
        if hasattr(self.model, "building"):
            return self.filter(building__organization_id=org_id)

        # Check if accessible via location -> building
        if hasattr(self.model, "location"):
            return self.filter(location__building__organization_id=org_id)

        # Check if accessible via campus
        if hasattr(self.model, "campus"):
            return self.filter(campus__organization_id=org_id)

        return self

    def for_campus(self, *, campus_id: int | None = None):
        """Filter by Campus (MSP mode only).

        Args:
            campus_id: Campus ID

        Returns:
            Filtered queryset (or unfiltered if MSP disabled or campus_id is None)
        """
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return self  # No-op if MSP disabled

        if campus_id is None:
            return self

        # Check if model has direct campus FK
        if hasattr(self.model, "campus_id"):
            return self.filter(campus_id=campus_id)

        # Check if accessible via building
        if hasattr(self.model, "building"):
            return self.filter(building__campus_id=campus_id)

        # Check if accessible via location -> building
        if hasattr(self.model, "location"):
            return self.filter(location__building__campus_id=campus_id)

        return self

    def for_user(self, *, user: User):
        """Smart filtering based on tenant mode and user permissions.

        Priority:
        1. Superuser → all data (unless MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
        2. MSP mode → user's organizations only
        3. Multi-site mode → user's site only
        4. Single-site → monitoring group filtering (existing behavior)

        Args:
            user: User instance

        Returns:
            Filtered queryset based on user permissions
        """
        # Superuser override
        if user.is_superuser:
            if getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True):
                return self
            # Fall through to org filtering

        # MSP mode: filter by user's organizations
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            from micboard.multitenancy.models import OrganizationMembership

            user_orgs = OrganizationMembership.objects.filter(
                user=user, is_active=True
            ).values_list("organization_id", flat=True)

            if not user_orgs:
                return self.none()

            # Apply org filtering
            qs = self
            for org_id in user_orgs:
                qs = qs.for_organization(organization=org_id)
            return qs

        # Multi-site mode: filter by site
        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self.for_site()

        # Single-site mode: use existing monitoring group logic
        # This preserves backward compatibility
        if hasattr(self, "_original_for_user"):
            return self._original_for_user(user)

        # Fallback: check for monitoring group filtering
        if hasattr(self.model, "location"):
            if user.is_superuser:
                return self

            user_locations = (
                user.monitoring_groups.filter(is_active=True)
                .values_list("monitoringgrouplocation__location", flat=True)
                .distinct()
            )

            if not user_locations.exists():
                return self.none()

            return self.filter(location__in=user_locations)

        return self


class TenantAwareManager(models.Manager):
    """Manager with tenant-aware filtering.

    Provides consistent interface for site/org/campus filtering
    across all deployment modes.
    """

    def get_queryset(self) -> TenantAwareQuerySet:
        """Return tenant-aware queryset."""
        return TenantAwareQuerySet(self.model, using=self._db)

    def for_site(self, *, site_id: int | None = None):
        """Filter by Django Site."""
        return self.get_queryset().for_site(site_id=site_id)

    def for_organization(self, *, organization: Organization | int | None = None):
        """Filter by Organization."""
        return self.get_queryset().for_organization(organization=organization)

    def for_campus(self, *, campus_id: int | None = None):
        """Filter by Campus."""
        return self.get_queryset().for_campus(campus_id=campus_id)

    def for_user(self, *, user: User):
        """Filter by user permissions."""
        return self.get_queryset().for_user(user=user)
