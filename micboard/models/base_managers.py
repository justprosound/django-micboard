"""Enhanced model managers with tenant support and optimizations.

Base classes for all models to support:
- Multi-tenancy (organization, campus, site)
- Optimization hints (select_related, prefetch_related)
- Common filtering patterns
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from django.conf import settings as django_settings
from django.db import models
from django.db.models import Q

from micboard.settings.deployment_controls import deployment_controls

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


def tenant_lookups(model: type[models.Model]) -> tuple[str, str | None] | None:
    """Return the organization and campus lookups that reach ``model``'s tenant owner.

    Returns None when the model has no reviewed ownership path; callers must fail closed.
    """
    model_label = getattr(getattr(model, "_meta", None), "label_lower", "")
    explicit_lookups = _EXPLICIT_TENANT_LOOKUPS.get(model_label)
    if explicit_lookups is not None:
        return explicit_lookups
    if hasattr(model, "organization_id"):
        campus_lookup = "campus_id" if hasattr(model, "campus_id") else None
        return "organization_id", campus_lookup
    for attribute, lookups in _RELATIONSHIP_TENANT_LOOKUPS:
        if hasattr(model, attribute):
            return lookups
    return None


def site_lookup(model: type[models.Model]) -> str | None:
    """Return the lookup that reaches ``model``'s Django Site, or None when it has none."""
    if hasattr(model, "site_id"):
        return "site_id"
    model_label = getattr(getattr(model, "_meta", None), "label_lower", "")
    explicit_lookup = _EXPLICIT_SITE_LOOKUPS.get(model_label)
    if explicit_lookup is not None:
        return explicit_lookup
    for attribute, lookup in _RELATIONSHIP_SITE_LOOKUPS:
        if hasattr(model, attribute):
            return lookup
    return None


def membership_filter(
    model: type[models.Model],
    memberships: Sequence[tuple[int, int | None]],
) -> Q | None:
    """Return a filter matching rows owned by any of the given memberships.

    Returns None when nothing can match: the model has no ownership path, no memberships were
    given, or every membership is campus-limited and the model has no campus to check.
    """
    lookups = tenant_lookups(model)
    if lookups is None:
        return None
    organization_lookup, campus_lookup = lookups

    tenant_filter: Q | None = None
    for organization_id, campus_id in memberships:
        scope = Q(**{organization_lookup: organization_id})
        if campus_id is not None:
            if campus_lookup is None:
                if organization_lookup != "pk":
                    continue
            else:
                scope &= Q(**{campus_lookup: campus_id})
        tenant_filter = scope if tenant_filter is None else tenant_filter | scope
    return tenant_filter


class TenantOptimizedQuerySet(models.QuerySet[_ModelT]):
    """Base QuerySet with the canonical tenant and site filters.

    Deciding which rows a user may see is not this queryset's job; ask
    `micboard.services.shared.visibility.visible_to`.
    """

    def supports_membership_scope(self) -> bool:
        """Return whether this model has an explicit tenant ownership path."""
        return tenant_lookups(self.model) is not None

    def for_site(self, *, site_id: int | None = None) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter by Django Site (multi-site mode)."""
        if not deployment_controls.multi_site_mode:
            return self

        site_id = site_id or getattr(django_settings, "SITE_ID", 1)

        lookup = site_lookup(self.model)
        if lookup is None:
            return self.none()
        return self.filter(**{lookup: site_id}).distinct()

    def for_memberships(
        self,
        memberships: Sequence[tuple[int, int | None]],
    ) -> TenantOptimizedQuerySet[_ModelT]:
        """Filter through explicit organization/campus membership identifiers."""
        tenant_filter = membership_filter(self.model, memberships)
        if tenant_filter is None:
            return self.none()
        return self.filter(tenant_filter).distinct()
