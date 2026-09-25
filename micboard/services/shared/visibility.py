"""Answer "which rows of this model may this user see", in one place.

Visibility is two rules intersected:

- **Tenant boundary.** Which organization, campus, or site owns the row. Models declare how
  to reach their owner in `micboard.models.base_managers`; a model with no ownership path is
  invisible to restricted users in MSP mode.
- **Monitoring reach.** Which rows the user's active monitoring groups cover, through the
  locations, channels, or assignments assigned to those groups. Models reach groups through
  the paths declared in `_REACH` below, or through their ``location`` relation by convention.
  A model with neither is not narrowed by monitoring groups.

How the two combine depends on the deployment and the user:

========================  =========================================================
Single-site               Superusers see every row. Everyone else sees monitoring reach.
Multi-site, no MSP        As single-site, inside the current site.
MSP                       Superusers with cross-organization view see every tenant.
                          Otherwise each membership contributes its tenant: the whole
                          tenant for administrators, owners, and superusers, and only
                          monitoring reach inside it for viewers and operators. In
                          multi-site mode, everything stays inside the current site.
========================  =========================================================

Anonymous and inactive accounts see nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import models, router
from django.db.models import Q, QuerySet

from micboard.models.base_managers import membership_filter, site_lookup
from micboard.services.shared.tenant_principal import TenantPrincipal


@dataclass(frozen=True)
class _Reach:
    """The user's monitoring coverage, as subqueries."""

    groups: QuerySet[Any]
    all_room_building_ids: QuerySet[Any]
    mode: str


_ReachRule = Callable[[_Reach], Q]


def _through_location(path: str) -> _ReachRule:
    """Reach rows whose location is assigned to a group, or sits in an all-rooms building."""
    prefix = f"{path}__" if path else ""

    def rule(reach: _Reach) -> Q:
        return Q(**{f"{prefix}monitoring_groups__in": reach.groups}) | Q(
            **{f"{prefix}building_id__in": reach.all_room_building_ids}
        )

    return rule


def _through_channel(path: str) -> _ReachRule:
    """Reach rows whose RF channel is assigned to a group directly."""
    prefix = f"{path}__" if path else ""

    def rule(reach: _Reach) -> Q:
        return Q(**{f"{prefix}monitoring_groups__in": reach.groups})

    return rule


def _building(reach: _Reach) -> Q:
    return Q(locations__monitoring_groups__in=reach.groups) | Q(pk__in=reach.all_room_building_ids)


def _performer_assignment(reach: _Reach) -> Q:
    return Q(monitoring_group__in=reach.groups)


def _performer(reach: _Reach) -> Q:
    visibility = Q(assignments__monitoring_group__in=reach.groups)
    if reach.mode != "msp":
        # An operator must be able to pick an unassigned performer to create the first
        # assignment. MSP mode cannot expose a performer that no tenant owns.
        visibility |= Q(assignments__isnull=True)
    return visibility


_REACH: dict[str, tuple[_ReachRule, ...]] = {
    "micboard.location": (_through_location(""),),
    "micboard.building": (_building,),
    "micboard.room": (_through_location("locations"),),
    "micboard.wallsection": (_through_location("wall__location"),),
    "micboard.rfchannel": (_through_location("chassis__location"), _through_channel("")),
    "micboard.wirelessunit": (
        _through_location("base_chassis__location"),
        _through_channel("assigned_resource"),
    ),
    "micboard.performerassignment": (_performer_assignment,),
    "micboard.performer": (_performer,),
}


def _reach_rules(model: type[models.Model]) -> tuple[_ReachRule, ...] | None:
    """Return how ``model`` reaches monitoring groups, or None when groups do not narrow it."""
    rules = _REACH.get(model._meta.label_lower)
    if rules is not None:
        return rules
    if hasattr(model, "location"):
        return (_through_location("location"),)
    return None


def _apply_rules(
    rules: tuple[_ReachRule, ...],
    *,
    groups: QuerySet[Any],
    using: str,
    mode: str,
) -> Q:
    """Combine a model's reach rules for one set of monitoring groups."""
    from micboard.models.monitoring.group import MonitoringGroupLocation

    group_ids = groups.values("pk")
    reach = _Reach(
        groups=group_ids,
        all_room_building_ids=MonitoringGroupLocation._default_manager.using(using)
        .filter(monitoring_group__in=group_ids, include_all_rooms=True)
        .values("location__building_id"),
        mode=mode,
    )
    combined = rules[0](reach)
    for rule in rules[1:]:
        combined |= rule(reach)
    return combined


def _reach_filter(
    model: type[models.Model],
    *,
    user: Any,
    principal: TenantPrincipal,
    using: str,
) -> Q | None:
    """Return the rows of ``model`` the user's groups reach, or None when groups do not apply."""
    rules = _reach_rules(model)
    if rules is None:
        return None

    from micboard.models.monitoring.group import MonitoringGroup

    groups = MonitoringGroup._default_manager.using(using).filter(
        users__pk=user.pk,
        is_active=True,
    )
    return _apply_rules(rules, groups=groups, using=using, mode=principal.mode)


def _site_filter(model: type[models.Model], principal: TenantPrincipal) -> Q | None:
    """Return the current-site filter, an empty filter when unbounded, or None for no rows."""
    if principal.site_id is None:
        return Q()
    lookup = site_lookup(model)
    if lookup is None:
        return None
    return Q(**{lookup: principal.site_id})


def _tenant_filter(
    model: type[models.Model],
    *,
    user: Any,
    principal: TenantPrincipal,
    using: str,
) -> Q | None:
    """Return the MSP membership filter with each membership's role applied."""
    whole = [m.scope for m in principal.memberships if principal.sees_whole_tenant(m)]
    narrowed = [m.scope for m in principal.memberships if not principal.sees_whole_tenant(m)]
    parts: list[Q] = []
    whole_filter = membership_filter(model, whole)
    if whole_filter is not None:
        parts.append(whole_filter)
    narrowed_filter = membership_filter(model, narrowed)
    if narrowed_filter is not None:
        reach = _reach_filter(model, user=user, principal=principal, using=using)
        parts.append(narrowed_filter if reach is None else narrowed_filter & reach)
    if not parts:
        return None
    combined = parts[0]
    for part in parts[1:]:
        combined |= part
    return combined


def _monitoring_group_filter(*, user: Any, principal: TenantPrincipal, using: str) -> Q | None:
    """Return the monitoring groups a user may see.

    Groups are not owned by a tenant; they reach into tenants through their locations,
    channels, and assignments. Unrestricted users see every active group. Everyone else sees
    the active groups they belong to. Where a tenant or site boundary applies, a group is
    visible only while it reaches a building the user can see.
    """
    condition = (
        Q(is_active=True) if principal.unrestricted else Q(is_active=True, users__pk=user.pk)
    )
    if principal.mode == "single":
        return condition

    from micboard.models.locations.structure import Building

    buildings = visible_to(Building, user=user, using=using).values("pk")
    return condition & (
        Q(locations__building_id__in=buildings)
        | Q(channels__chassis__location__building_id__in=buildings)
        | Q(performer_assignments__wireless_unit__base_chassis__location__building_id__in=buildings)
    )


def visibility_filter(
    model: type[models.Model],
    *,
    user: Any,
    using: str | None = None,
    monitoring_reach: bool = True,
) -> Q | None:
    """Return the filter selecting the rows of ``model`` that ``user`` may see.

    With ``monitoring_reach=False`` only the tenant and site boundary applies, as if every
    membership saw its whole tenant. An empty ``Q()`` means every row; None means no row.
    """
    database = using or router.db_for_read(model)
    principal = TenantPrincipal.resolve(user, using=database)
    if not principal.authenticated:
        return None
    if model._meta.label_lower == "micboard.monitoringgroup":
        return _monitoring_group_filter(user=user, principal=principal, using=database)

    site = _site_filter(model, principal)
    if site is None:
        return None

    if principal.mode == "msp":
        if principal.unrestricted:
            return site
        if not monitoring_reach:
            tenant = membership_filter(model, principal.scopes())
        else:
            tenant = _tenant_filter(model, user=user, principal=principal, using=database)
        return None if tenant is None else tenant & site

    if principal.superuser or not monitoring_reach:
        return site
    reach = _reach_filter(model, user=user, principal=principal, using=database)
    return site if reach is None else reach & site


def _apply(model: type[models.Model], condition: Q | None, database: str) -> QuerySet[Any]:
    manager = getattr(model, "objects", model._default_manager)
    queryset: QuerySet[Any] = manager.using(database).all()
    if condition is None:
        return queryset.none()
    if not condition:
        return queryset
    visible_ids = model._base_manager.db_manager(database).filter(condition).values("pk")
    return queryset.filter(pk__in=visible_ids)


def visible_to(
    model: type[models.Model],
    *,
    user: Any,
    using: str | None = None,
) -> QuerySet[Any]:
    """Return the rows of ``model`` that ``user`` may see on operator surfaces.

    The result is a plain filter on the model's default manager, so callers can keep
    chaining, locking, or updating it. The tenant boundary is resolved on the database being
    asked about, not whichever database the manager defaults to.
    """
    database = using or router.db_for_read(model)
    return _apply(model, visibility_filter(model, user=user, using=database), database)


def restrict_to_tenant_boundary(queryset: QuerySet[Any], *, user: Any) -> QuerySet[Any]:
    """Narrow ``queryset`` to rows inside the user's tenant and site boundary.

    Monitoring groups do not narrow this. The Django admin uses it: staff read their whole
    tenant there, and mutation is gated separately by membership role. The queryset comes
    back unchanged when no boundary applies.
    """
    model = queryset.model
    condition = visibility_filter(model, user=user, using=queryset.db, monitoring_reach=False)
    if condition is None:
        return queryset.none()
    if not condition:
        return queryset
    inside = model._base_manager.db_manager(queryset.db).filter(condition).values("pk")
    return queryset.filter(pk__in=inside)


def reaches(group: Any, obj: models.Model) -> bool:
    """Return whether one monitoring group covers ``obj`` through the declared reach paths.

    Returns True for a model that monitoring groups do not narrow.
    """
    rules = _reach_rules(obj.__class__)
    if rules is None:
        return True

    from micboard.models.monitoring.group import MonitoringGroup

    database = obj._state.db or router.db_for_read(obj.__class__)
    groups = MonitoringGroup._default_manager.using(database).filter(pk=group.pk)
    condition = _apply_rules(rules, groups=groups, using=database, mode="msp")
    return obj.__class__._base_manager.db_manager(database).filter(condition, pk=obj.pk).exists()
