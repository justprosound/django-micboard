"""Tenant visibility policy for stored setting overrides."""

from __future__ import annotations

from typing import Any, cast

from django.apps import apps
from django.conf import settings as django_settings
from django.db.models import F, Q

from micboard.services.settings.dtos import SettingsVisibilityScope
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.access_policy import TENANT_ADMIN_ROLES
from micboard.settings.scope_policy import (
    resolve_scope,
)


class SettingsVisibilityService:
    """Resolve and apply the setting scopes a user may inspect."""

    @staticmethod
    def is_unrestricted(scope: SettingsVisibilityScope) -> bool:
        """Return whether every stored setting scope is available."""
        return (
            scope.organization_ids is None
            and scope.site_ids is None
            and scope.manufacturer_ids is None
        )

    def for_user(self, *, user: Any) -> SettingsVisibilityScope:
        """Resolve the setting-override identifiers visible to ``user``."""
        return self._for_user(user=user, roles=None)

    def for_management_user(self, *, user: Any) -> SettingsVisibilityScope:
        """Resolve setting scopes where ``user`` has an administering role."""
        return self._for_user(user=user, roles=TENANT_ADMIN_ROLES)

    def _for_user(
        self,
        *,
        user: Any,
        roles: frozenset[str] | None,
    ) -> SettingsVisibilityScope:
        """Resolve readable or role-filtered management scope for ``user``."""
        msp_enabled = micboard_settings.msp_enabled
        multi_site_mode = micboard_settings.multi_site_mode
        cross_org_view = micboard_settings.allow_cross_org_view

        if not msp_enabled:
            if not multi_site_mode:
                return SettingsVisibilityScope()
            return SettingsVisibilityScope(
                organization_ids=frozenset(),
                site_ids=frozenset({getattr(django_settings, "SITE_ID", 1)}),
                manufacturer_ids=frozenset(),
            )

        if not apps.is_installed("micboard.multitenancy"):
            return SettingsVisibilityScope(
                organization_ids=frozenset(),
                site_ids=frozenset(),
                manufacturer_ids=frozenset(),
            )

        from micboard.multitenancy.models import Organization, OrganizationMembership

        site_id = getattr(django_settings, "SITE_ID", 1)
        if user.is_superuser and cross_org_view:
            if not multi_site_mode:
                return SettingsVisibilityScope()
            organization_ids = frozenset(
                Organization._default_manager.filter(
                    is_active=True,
                    site_id=site_id,
                ).values_list("pk", flat=True)
            )
            return SettingsVisibilityScope(
                organization_ids=organization_ids,
                site_ids=frozenset({site_id}),
                manufacturer_ids=frozenset(),
            )

        memberships_queryset = OrganizationMembership._default_manager.filter(
            Q(campus__isnull=True)
            | Q(
                campus__is_active=True,
                campus__organization_id=F("organization_id"),
            ),
            user=user,
            is_active=True,
            organization__is_active=True,
        )
        if roles is not None:
            memberships_queryset = memberships_queryset.filter(role__in=roles)
        if multi_site_mode:
            memberships_queryset = memberships_queryset.filter(organization__site_id=site_id)
        memberships = list(memberships_queryset.values_list("organization_id", "campus_id"))
        # A campus-limited membership must not grant organization-wide setting
        # access.  Organization settings affect sibling campuses, so only an
        # explicitly organization-wide membership can manage them.
        organization_ids = frozenset(
            organization_id for organization_id, campus_id in memberships if campus_id is None
        )

        return SettingsVisibilityScope(
            organization_ids=organization_ids,
            site_ids=frozenset(),
            manufacturer_ids=frozenset(),
        )

    @classmethod
    def has_manageable_scope(cls, scope: SettingsVisibilityScope) -> bool:
        """Return whether at least one setting target may be mutated."""
        return cls.is_unrestricted(scope) or any(
            bool(identifiers)
            for identifiers in (
                scope.organization_ids,
                scope.site_ids,
                scope.manufacturer_ids,
            )
        )

    @staticmethod
    def build_filter(
        scope: SettingsVisibilityScope,
        *,
        include_global: bool = True,
    ) -> Q:
        """Build an exact-scope filter for stored setting rows."""
        visibility_filter = Q(pk__isnull=True)
        if include_global:
            visibility_filter |= Q(
                organization_id__isnull=True,
                site_id__isnull=True,
                manufacturer_id__isnull=True,
            )

        if scope.organization_ids is None:
            visibility_filter |= Q(
                organization_id__isnull=False,
                site_id__isnull=True,
                manufacturer_id__isnull=True,
            )
        elif scope.organization_ids:
            visibility_filter |= Q(
                organization_id__in=scope.organization_ids,
                site_id__isnull=True,
                manufacturer_id__isnull=True,
            )

        if scope.site_ids is None:
            visibility_filter |= Q(
                organization_id__isnull=True,
                site_id__isnull=False,
                manufacturer_id__isnull=True,
            )
        elif scope.site_ids:
            visibility_filter |= Q(
                organization_id__isnull=True,
                site_id__in=scope.site_ids,
                manufacturer_id__isnull=True,
            )

        if scope.manufacturer_ids is None:
            visibility_filter |= Q(
                organization_id__isnull=True,
                site_id__isnull=True,
                manufacturer_id__isnull=False,
            )
        elif scope.manufacturer_ids:
            visibility_filter |= Q(
                organization_id__isnull=True,
                site_id__isnull=True,
                manufacturer_id__in=scope.manufacturer_ids,
            )

        return visibility_filter

    @classmethod
    def build_management_filter(cls, scope: SettingsVisibilityScope) -> Q:
        """Return rows a user may mutate, excluding global rows when restricted."""
        return cls.build_filter(
            scope,
            include_global=cls.is_unrestricted(scope),
        )

    @classmethod
    def can_manage_scope(
        cls,
        scope: SettingsVisibilityScope,
        *,
        organization_id: int | None,
        site_id: int | None,
        manufacturer_id: int | None,
    ) -> bool:
        """Authorize one exact setting scope against a user's visibility."""
        resolved_scope = resolve_scope(
            organization_id=organization_id,
            site_id=site_id,
            manufacturer_id=manufacturer_id,
        )
        if resolved_scope == "global":
            return cls.is_unrestricted(scope)
        if resolved_scope is None:
            return False

        if resolved_scope == "organization":
            return (
                scope.organization_ids is None
                or cast(int, organization_id) in scope.organization_ids
            )
        if resolved_scope == "site":
            return scope.site_ids is None or cast(int, site_id) in scope.site_ids
        return (
            scope.manufacturer_ids is None or cast(int, manufacturer_id) in scope.manufacturer_ids
        )


settings_visibility = SettingsVisibilityService()
