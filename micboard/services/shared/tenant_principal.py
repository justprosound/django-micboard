"""Resolve who a user is, tenant-wise, once.

Every access decision starts from the same facts: the deployment mode, whether the user is a
superuser, and which organization or campus memberships are genuinely active. An active
membership is one whose own row, organization, and (when it names one) campus are active, and
whose campus belongs to its organization. In multi-site mode it must also belong to the
current site. `active_memberships` is the only place that query is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

from django.apps import apps
from django.conf import settings as django_settings
from django.db.models import F, Q

from micboard.services.settings.settings_service import settings as micboard_settings

ADMIN_ROLES: Final[frozenset[str]] = frozenset({"admin", "owner"})
"""Roles that administer their tenant and see all of it."""

MODIFY_ROLES: Final[frozenset[str]] = frozenset({"operator", "admin", "owner"})
"""Roles that may change device assignments."""

DeploymentMode = Literal["single", "site", "msp"]


@dataclass(frozen=True)
class Membership:
    """One active organization membership, optionally limited to a campus."""

    organization_id: int
    campus_id: int | None
    role: str

    @property
    def scope(self) -> tuple[int, int | None]:
        """Return the ``(organization_id, campus_id)`` pair tenant filters take."""
        return self.organization_id, self.campus_id

    def covers(self, *, organization_id: int, campus_id: int | None) -> bool:
        """Return whether this membership reaches a row owned by that organization and campus."""
        if self.organization_id != organization_id:
            return False
        return self.campus_id is None or self.campus_id == campus_id


def deployment_mode() -> DeploymentMode:
    """Return the tenant boundary the deployment enforces."""
    if micboard_settings.msp_enabled:
        return "msp"
    if micboard_settings.multi_site_mode:
        return "site"
    return "single"


def current_site_id() -> int:
    """Return the Django Site this process serves."""
    return int(getattr(django_settings, "SITE_ID", 1))


def active_memberships(
    user_id: int,
    *,
    using: str | None = None,
    roles: frozenset[str] | None = None,
) -> tuple[Membership, ...]:
    """Return the user's active memberships, newest first, optionally limited to some roles.

    Returns an empty tuple when the multitenancy app is not installed or the user account is
    inactive, so a revoked account holds no tenant.
    """
    if not apps.is_installed("micboard.multitenancy"):
        return ()

    from micboard.multitenancy.models import OrganizationMembership

    manager = OrganizationMembership._default_manager
    if using is not None:
        manager = manager.db_manager(using)
    rows = manager.filter(
        Q(campus__isnull=True)
        | Q(campus__is_active=True, campus__organization_id=F("organization_id")),
        user_id=user_id,
        user__is_active=True,
        is_active=True,
        organization__is_active=True,
    )
    if roles is not None:
        rows = rows.filter(role__in=roles)
    if micboard_settings.multi_site_mode:
        rows = rows.filter(organization__site_id=current_site_id())
    return tuple(
        Membership(organization_id=organization_id, campus_id=campus_id, role=role)
        for organization_id, campus_id, role in rows.order_by("-created_at", "-pk").values_list(
            "organization_id", "campus_id", "role"
        )
    )


@dataclass(frozen=True)
class TenantPrincipal:
    """The tenant facts every access decision about one user starts from.

    Attributes:
        authenticated: False for anonymous and inactive accounts, which see nothing.
        superuser: Whether the account is a platform superuser.
        mode: The deployment's tenant boundary.
        unrestricted: Whether the user crosses every organization boundary. The site
            boundary still applies.
        site_id: The Django Site every row must belong to in multi-site mode, else None.
        memberships: Active memberships; resolved only in MSP mode for restricted users.
    """

    authenticated: bool
    superuser: bool
    mode: DeploymentMode
    unrestricted: bool
    site_id: int | None = None
    memberships: tuple[Membership, ...] = ()

    @classmethod
    def resolve(cls, user: Any, *, using: str | None = None) -> TenantPrincipal:
        """Resolve ``user`` with at most one membership query."""
        mode = deployment_mode()
        site_id = current_site_id() if micboard_settings.multi_site_mode else None
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", True):
            return cls(
                authenticated=False,
                superuser=False,
                mode=mode,
                unrestricted=False,
                site_id=site_id,
            )

        superuser = bool(getattr(user, "is_superuser", False))
        if mode != "msp":
            # Single-site and plain multi-site deployments have no organization boundary, so
            # the cross-organization switch has nothing to widen.
            return cls(
                authenticated=True,
                superuser=superuser,
                mode=mode,
                unrestricted=superuser,
                site_id=site_id,
            )
        if superuser and micboard_settings.allow_cross_org_view:
            return cls(
                authenticated=True,
                superuser=True,
                mode=mode,
                unrestricted=True,
                site_id=site_id,
            )
        return cls(
            authenticated=True,
            superuser=superuser,
            mode=mode,
            unrestricted=False,
            site_id=site_id,
            memberships=active_memberships(user.pk, using=using),
        )

    def sees_whole_tenant(self, membership: Membership) -> bool:
        """Return whether this membership shows its whole tenant rather than group reach.

        Administrators administer their tenant, so they see all of it. A superuser without
        cross-organization view is limited to the tenants it belongs to, but not further
        narrowed by monitoring groups. Viewers and operators see only what their monitoring
        groups reach.
        """
        return self.superuser or membership.role in ADMIN_ROLES

    def scopes(self, *, roles: frozenset[str] | None = None) -> list[tuple[int, int | None]]:
        """Return membership scopes, optionally limited to some roles."""
        return [m.scope for m in self.memberships if roles is None or m.role in roles]

    def has_role_for(
        self,
        roles: frozenset[str],
        *,
        organization_id: int,
        campus_id: int | None,
    ) -> bool:
        """Return whether a membership with one of ``roles`` covers that tenant."""
        return any(
            m.role in roles and m.covers(organization_id=organization_id, campus_id=campus_id)
            for m in self.memberships
        )
