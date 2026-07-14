"""Enhanced model managers with tenant support and optimizations.

Base classes for all models to support:
- Multi-tenancy (organization, campus, site)
- Optimization hints (select_related, prefetch_related)
- Common filtering patterns
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import F, Q

_ModelT = TypeVar("_ModelT", bound=models.Model)


class OrganizationLike(Protocol):
    """Structural tenant identifier accepted by queryset filters."""

    id: int


# Models whose tenant owner is reached through a domain-specific relation rather
# than one of the generic direct-field conventions below. Keep these mappings
# explicit: a missing ownership path must continue to fail closed.
_EXPLICIT_TENANT_LOOKUPS: dict[str, tuple[str, str | None]] = {
    "micboard_multitenancy.organization": ("pk", None),
    "micboard_multitenancy.campus": ("organization_id", "pk"),
    "micboard.alert": (
        "channel__chassis__location__building__organization_id",
        "channel__chassis__location__building__campus_id",
    ),
    "micboard.chargerslot": (
        "charger__location__building__organization_id",
        "charger__location__building__campus_id",
    ),
    "micboard.devicemovementlog": (
        "device__location__building__organization_id",
        "device__location__building__campus_id",
    ),
    "micboard.wallsection": (
        "wall__location__building__organization_id",
        "wall__location__building__campus_id",
    ),
}

_EXPLICIT_SITE_LOOKUPS: dict[str, str] = {
    "micboard.alert": "channel__chassis__location__building__site_id",
    "micboard.chargerslot": "charger__location__building__site_id",
    "micboard.devicemovementlog": "device__location__building__site_id",
    "micboard.wallsection": "wall__location__building__site_id",
}

_RELATIONSHIP_TENANT_LOOKUPS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("building", ("building__organization_id", "building__campus_id")),
    ("location", ("location__building__organization_id", "location__building__campus_id")),
    (
        "base_chassis",
        (
            "base_chassis__location__building__organization_id",
            "base_chassis__location__building__campus_id",
        ),
    ),
    (
        "chassis",
        (
            "chassis__location__building__organization_id",
            "chassis__location__building__campus_id",
        ),
    ),
    (
        "wireless_unit",
        (
            "wireless_unit__base_chassis__location__building__organization_id",
            "wireless_unit__base_chassis__location__building__campus_id",
        ),
    ),
    (
        "assignments",
        (
            "assignments__wireless_unit__base_chassis__location__building__organization_id",
            "assignments__wireless_unit__base_chassis__location__building__campus_id",
        ),
    ),
    ("campus", ("campus__organization_id", "campus_id")),
)

_RELATIONSHIP_SITE_LOOKUPS: tuple[tuple[str, str], ...] = (
    ("building", "building__site_id"),
    ("location", "location__building__site_id"),
    ("base_chassis", "base_chassis__location__building__site_id"),
    ("chassis", "chassis__location__building__site_id"),
    ("wireless_unit", "wireless_unit__base_chassis__location__building__site_id"),
    ("assignments", "assignments__wireless_unit__base_chassis__location__building__site_id"),
    ("organization", "organization__site_id"),
    ("campus", "campus__organization__site_id"),
)


class TenantOptimizedQuerySet(models.QuerySet[_ModelT]):
    """Base QuerySet with tenant filtering and optimization methods.

    Provides the canonical tenant filters and common ORM optimizations.
    """

    def _tenant_lookups(self) -> tuple[str, str | None] | None:
        """Return organization and campus lookups for the queryset model."""
        model_label = getattr(getattr(self.model, "_meta", None), "label_lower", "")
        explicit_lookups = _EXPLICIT_TENANT_LOOKUPS.get(model_label)
        if explicit_lookups is not None:
            return explicit_lookups
        if hasattr(self.model, "organization_id"):
            campus_lookup = "campus_id" if hasattr(self.model, "campus_id") else None
            return "organization_id", campus_lookup
        for attribute, lookups in _RELATIONSHIP_TENANT_LOOKUPS:
            if hasattr(self.model, attribute):
                return lookups
        return None

    def _campus_lookup(self) -> str | None:
        """Return the campus lookup for the queryset model, when available."""
        if hasattr(self.model, "campus_id"):
            return "campus_id"
        lookups = TenantOptimizedQuerySet._tenant_lookups(self)
        return lookups[1] if lookups is not None else None

    def _site_lookup(self) -> str | None:
        """Return the Django Site lookup for the queryset model."""
        model_label = getattr(getattr(self.model, "_meta", None), "label_lower", "")
        if hasattr(self.model, "site_id"):
            return "site_id"
        explicit_lookup = _EXPLICIT_SITE_LOOKUPS.get(model_label)
        if explicit_lookup is not None:
            return explicit_lookup
        for attribute, lookup in _RELATIONSHIP_SITE_LOOKUPS:
            if hasattr(self.model, attribute):
                return lookup
        return None

    def for_site(self, *, site_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Django Site (multi-site mode)."""
        if not getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            return self

        site_id = site_id or getattr(settings, "SITE_ID", 1)

        site_lookup = TenantOptimizedQuerySet._site_lookup(self)
        if site_lookup is None:
            return self.none()
        return self.filter(**{site_lookup: site_id}).distinct()

    def for_organization(
        self, *, organization: OrganizationLike | int | None = None
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

    def for_memberships(
        self,
        memberships: Sequence[tuple[int, int | None]],
    ) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter through explicit organization/campus membership identifiers."""
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

        multi_site_enabled = getattr(settings, "MICBOARD_MULTI_SITE_MODE", False)
        if user.is_superuser and getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True):
            return self.for_site() if multi_site_enabled else self

        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            if not apps.is_installed("micboard.multitenancy"):
                return self.none()

            memberships = list(
                user.org_memberships.filter(
                    Q(campus__isnull=True)
                    | Q(
                        campus__is_active=True,
                        campus__organization_id=F("organization_id"),
                    ),
                    is_active=True,
                    organization__is_active=True,
                ).values_list("organization_id", "campus_id")
            )

            if not memberships:
                return self.none()

            queryset = self.for_memberships(memberships)
            if multi_site_enabled:
                return queryset.for_site()
            return queryset

        if multi_site_enabled:
            return self.for_site()

        # Single-site: use monitoring group filtering if available
        if hasattr(self.model, "location") and hasattr(user, "monitoring_groups"):
            groups = user.monitoring_groups.filter(is_active=True)
            all_room_buildings = groups.filter(
                monitoringgrouplocation__include_all_rooms=True
            ).values_list("monitoringgrouplocation__location__building_id", flat=True)
            return self.filter(
                Q(location__monitoring_groups__in=groups)
                | Q(location__building_id__in=all_room_buildings)
            ).distinct()

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
        self, *, organization: OrganizationLike | int | None = None
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
