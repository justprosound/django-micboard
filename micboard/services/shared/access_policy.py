"""Shared policy for tenant-wide read and mutation access decisions."""

from __future__ import annotations

from typing import Any, Final

from django.apps import apps
from django.conf import settings as django_settings
from django.db import models
from django.db.models import Exists, F, OuterRef, Q

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.services.settings.settings_service import settings as micboard_settings

TENANT_ADMIN_ROLES = frozenset({"admin", "owner"})

# Explicit host-wide administration surfaces. These models do not carry a
# tenant key, so only a platform superuser may mutate them in tenant-aware
# deployments. Every new entry requires an ownership review.
PLATFORM_GLOBAL_ADMIN_MODEL_LABELS: Final[frozenset[str]] = frozenset(
    {
        "micboard.activitylog",
        "micboard.configurationauditlog",
        "micboard.discovereddevice",
        "micboard.discoverycidr",
        "micboard.discoveryfqdn",
        "micboard.discoveryjob",
        "micboard.discoveryqueue",
        "micboard.manufacturer",
        "micboard.manufacturerapiserver",
        "micboard.manufacturerconfiguration",
        "micboard.micboardconfig",
        "micboard.servicesynclog",
        "micboard.settingdefinition",
        "micboard.useralertpreference",
    }
)

# A performer can be shared by assignments in multiple tenants. Existential
# tenant filtering is sufficient for reading it, but mutation must prove that
# every owning assignment is writable by the caller.
SHARED_TENANT_OWNERSHIP_MODEL_LABELS: Final[frozenset[str]] = frozenset({"micboard.performer"})


def has_unrestricted_tenant_access(user: Any) -> bool:
    """Return whether ``user`` may bypass organization membership boundaries."""
    return bool(getattr(user, "is_superuser", False) and micboard_settings.allow_cross_org_view)


class TenantRoleAccessService:
    """Apply MSP membership roles without narrowing read-only visibility."""

    management_roles = TENANT_ADMIN_ROLES

    @staticmethod
    def _tenant_mode_enabled() -> bool:
        """Return whether a tenant or site mutation boundary is active."""
        return bool(micboard_settings.msp_enabled or micboard_settings.multi_site_mode)

    @classmethod
    def management_memberships(
        cls,
        *,
        user: Any,
        using: str | None = None,
    ) -> list[tuple[int, int | None]]:
        """Return active organization/campus scopes where ``user`` may administer."""
        if not micboard_settings.msp_enabled or not apps.is_installed("micboard.multitenancy"):
            return []

        from micboard.multitenancy.models import OrganizationMembership

        database = using or getattr(getattr(user, "_state", None), "db", None)
        membership_manager = OrganizationMembership._default_manager
        if database is not None:
            membership_manager = membership_manager.db_manager(database)
        memberships = membership_manager.filter(
            Q(campus__isnull=True)
            | Q(
                campus__is_active=True,
                campus__organization_id=F("organization_id"),
            ),
            user=user,
            is_active=True,
            organization__is_active=True,
            role__in=cls.management_roles,
        )
        if micboard_settings.multi_site_mode:
            memberships = memberships.filter(
                organization__site_id=getattr(django_settings, "SITE_ID", 1)
            )
        return list(memberships.values_list("organization_id", "campus_id"))

    @staticmethod
    def is_platform_global_model(model: type[models.Model]) -> bool:
        """Return whether ``model`` is a reviewed host-wide admin surface."""
        return model._meta.label_lower in PLATFORM_GLOBAL_ADMIN_MODEL_LABELS

    @staticmethod
    def _has_platform_global_access(*, user: Any, model: type[models.Model]) -> bool:
        """Authorize host-wide catalogs independently from tenant view scope."""
        return bool(
            getattr(user, "is_superuser", False)
            and TenantRoleAccessService.is_platform_global_model(model)
        )

    @classmethod
    def _scope_shared_ownership(
        cls,
        queryset: models.QuerySet[Any],
        *,
        user: Any,
    ) -> models.QuerySet[Any]:
        """Require every owner of a shared performer to be writable."""
        if queryset.model._meta.label_lower not in SHARED_TENANT_OWNERSHIP_MODEL_LABELS:
            return queryset

        from micboard.models.monitoring.performer_assignment import PerformerAssignment

        all_owners = PerformerAssignment._base_manager.using(queryset.db).all()
        manageable_owner_ids = cls.scope_manageable_queryset(
            all_owners,
            user=user,
        ).values("pk")
        owners = all_owners.filter(performer_id=OuterRef("pk"))
        unmanageable_owners = owners.exclude(pk__in=manageable_owner_ids)
        return queryset.filter(Exists(owners), ~Exists(unmanageable_owners))

    @classmethod
    def scope_manageable_queryset(
        cls,
        queryset: models.QuerySet[Any],
        *,
        user: Any,
    ) -> models.QuerySet[Any]:
        """Intersect ``queryset`` with scopes where ``user`` has an admin role."""
        if not cls._tenant_mode_enabled():
            return queryset
        if cls.is_platform_global_model(queryset.model):
            return (
                queryset
                if cls._has_platform_global_access(user=user, model=queryset.model)
                else queryset.none()
            )
        if has_unrestricted_tenant_access(user):
            return queryset

        ownership_scope: TenantOptimizedQuerySet[Any] = TenantOptimizedQuerySet(
            queryset.model,
            using=queryset.db,
        )
        if not ownership_scope.supports_membership_scope():
            return queryset.none()

        if not micboard_settings.msp_enabled:
            site_scope = ownership_scope.for_site()
            manageable = queryset.filter(pk__in=site_scope.values("pk"))
            return cls._scope_shared_ownership(manageable, user=user)

        memberships = cls.management_memberships(user=user, using=queryset.db)
        if not memberships:
            return queryset.none()

        role_scope = ownership_scope.for_memberships(memberships)
        if micboard_settings.multi_site_mode:
            role_scope = role_scope.for_site()
        manageable = queryset.filter(pk__in=role_scope.values("pk"))
        return cls._scope_shared_ownership(manageable, user=user)

    @classmethod
    def can_add_model(cls, *, user: Any, model: type[models.Model]) -> bool:
        """Authorize adds only where a new row can carry exclusive tenant ownership."""
        if cls._has_platform_global_access(user=user, model=model):
            return True
        if (
            cls._tenant_mode_enabled()
            and model._meta.label_lower in SHARED_TENANT_OWNERSHIP_MODEL_LABELS
        ):
            return bool(
                has_unrestricted_tenant_access(user) and not micboard_settings.multi_site_mode
            )
        if has_unrestricted_tenant_access(user):
            return True
        return cls.can_manage_model(user=user, model=model)

    @classmethod
    def can_manage_model(cls, *, user: Any, model: type[models.Model]) -> bool:
        """Authorize adding or bulk-mutating rows of one tenant-owned model."""
        if not cls._tenant_mode_enabled():
            return True
        if cls.is_platform_global_model(model):
            return cls._has_platform_global_access(user=user, model=model)
        if has_unrestricted_tenant_access(user):
            return True
        if not TenantOptimizedQuerySet(model).supports_membership_scope():
            return False
        if not micboard_settings.msp_enabled:
            return True
        return bool(cls.management_memberships(user=user))

    @classmethod
    def can_manage_object(cls, *, user: Any, obj: models.Model) -> bool:
        """Authorize mutation only when the object's exact tenant role permits it."""
        if not cls._tenant_mode_enabled():
            return True
        if cls.is_platform_global_model(obj.__class__):
            return cls._has_platform_global_access(user=user, model=obj.__class__)
        if has_unrestricted_tenant_access(user):
            return True
        database = getattr(getattr(obj, "_state", None), "db", None)
        manager = obj.__class__._base_manager
        if database is not None:
            manager = manager.db_manager(database)
        queryset = manager.filter(pk=obj.pk)
        return cls.scope_manageable_queryset(queryset, user=user).exists()


tenant_role_access = TenantRoleAccessService()
