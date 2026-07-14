from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from django.core.exceptions import PermissionDenied
from django.db import router

from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.access_policy import tenant_role_access
from micboard.utils.dependencies import (
    HAS_IMPORT_EXPORT,
    HAS_RANGE_FILTER,
    HAS_SIMPLE_HISTORY,
    HAS_UNFOLD,
    HAS_UNFOLD_FILTERS,
    HAS_UNFOLD_IMPORT_EXPORT,
)

logger = logging.getLogger(__name__)

# Host-wide catalogs allowed in tenant-owned admin relationship widgets. Keep
# this list model-based and deliberately small: adding a label requires proving
# that its rows carry no organization, campus, or site ownership boundary.
SHARED_ADMIN_REFERENCE_MODEL_LABELS: Final[frozenset[str]] = frozenset(
    {
        "micboard.manufacturer",  # Host-wide hardware vendor catalog.
        "micboard.settingdefinition",  # Host-wide schema selected by Setting forms.
    }
)

# Base ModelAdmin - Use Unfold if available
if HAS_UNFOLD:
    from unfold.admin import ModelAdmin as BaseAdmin

    if HAS_UNFOLD_FILTERS:
        from unfold.contrib.filters.admin import RangeDateFilter, RangeDateTimeFilter
    else:
        RangeDateFilter = None
        RangeDateTimeFilter = None
else:
    from django.contrib.admin import ModelAdmin as BaseAdmin

    RangeDateFilter = None
    RangeDateTimeFilter = None


# 1. Import-Export Support
if TYPE_CHECKING or HAS_IMPORT_EXPORT:
    from import_export.admin import ImportExportModelAdmin as _ImportExportBase
else:
    _ImportExportBase = object


class BaseImportExportAdmin(_ImportExportBase):
    """Type-stable base for the optional import-export integration."""

    import_form_class: Any = None
    export_form_class: Any = None


if HAS_IMPORT_EXPORT and HAS_UNFOLD_IMPORT_EXPORT:
    try:
        from unfold.contrib.import_export.forms import ExportForm, ImportForm

        BaseImportExportAdmin.import_form_class = ImportForm
        BaseImportExportAdmin.export_form_class = ExportForm
    except ImportError:
        logger.debug("Unfold import-export forms are unavailable")


# 2. Simple History Support
if HAS_SIMPLE_HISTORY:
    from simple_history.admin import SimpleHistoryAdmin as BaseHistoryAdmin
else:

    class BaseHistoryAdmin:  # type: ignore
        pass


class EnhancedAdminMixin:
    """Combines optional admin improvements into a single mixin."""

    def get_list_filter(self, request: Any) -> list[Any]:
        """Upgrade date filters to range filters if available."""
        filters = list(super().get_list_filter(request))  # type: ignore

        # If using Unfold, we want to use Unfold's optimized filters
        if HAS_UNFOLD_FILTERS:
            new_filters: list[Any] = []
            for f in filters:
                if isinstance(f, str):
                    if f in ["created_at", "updated_at", "last_seen", "timestamp", "detected_at"]:
                        new_filters.append((f, RangeDateTimeFilter))
                    elif f in ["date", "assigned_at"]:
                        new_filters.append((f, RangeDateFilter))
                    else:
                        new_filters.append(f)
                else:
                    new_filters.append(f)
            return new_filters

        if not HAS_RANGE_FILTER:
            return filters

        from rangefilter.filters import DateRangeFilter, DateTimeRangeFilter

        range_filters: list[Any] = []
        for f in filters:
            if f in ["created_at", "updated_at", "last_seen", "timestamp", "detected_at"]:
                range_filters.append((f, DateTimeRangeFilter))
            elif f in ["date", "assigned_at"]:
                range_filters.append((f, DateRangeFilter))
            else:
                range_filters.append(f)
        return range_filters


class MicboardModelAdmin(EnhancedAdminMixin, BaseImportExportAdmin, BaseHistoryAdmin, BaseAdmin):
    """Base ModelAdmin with optional extras and tenant-safe query boundaries."""

    # Unfold specific default settings
    list_filter_submit = HAS_UNFOLD
    list_fullwidth = HAS_UNFOLD
    warn_unsaved_form = HAS_UNFOLD

    def has_import_permission(self, request: Any) -> bool:
        """Deny bulk imports until resources enforce request tenant scope."""
        return False

    def has_export_permission(self, request: Any) -> bool:
        """Deny bulk exports until resources enforce request tenant scope."""
        return False

    def has_add_permission(self, request: Any) -> bool:
        """Require both Django permission and an administering tenant role."""
        return bool(
            super().has_add_permission(request)
            and tenant_role_access.can_add_model(user=request.user, model=self.model)
        )

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        """Require an administering role for the exact object when available."""
        if not super().has_change_permission(request, obj):
            return False
        if obj is None:
            return tenant_role_access.can_manage_model(user=request.user, model=self.model)
        return tenant_role_access.can_manage_object(user=request.user, obj=obj)

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        """Require an administering role for every delete boundary."""
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None:
            return tenant_role_access.can_manage_model(user=request.user, model=self.model)
        return tenant_role_access.can_manage_object(user=request.user, obj=obj)

    @staticmethod
    def _scope_queryset_for_user(queryset: Any, *, user: Any) -> Any:
        """Intersect a queryset with the user's active tenant memberships.

        Models with a tenant-aware manager remain the source of truth. Standard
        managers use the same tenant lookup contract; models without a safe
        tenant path fail closed while MSP mode is enabled.
        """
        msp_enabled = micboard_settings.msp_enabled
        multi_site_enabled = micboard_settings.multi_site_mode
        if not (msp_enabled or multi_site_enabled):
            return queryset
        if (
            msp_enabled
            and not multi_site_enabled
            and user.is_superuser
            and micboard_settings.allow_cross_org_view
        ):
            return queryset

        if user.is_superuser and tenant_role_access.is_platform_global_model(queryset.model):
            return queryset

        manager = getattr(queryset.model, "objects", queryset.model._default_manager)
        manager_for_user = getattr(manager, "for_user", None)
        if callable(manager_for_user):
            visible_queryset = manager_for_user(user=user)
        else:
            from micboard.models.base_managers import TenantOptimizedQuerySet

            visible_queryset = TenantOptimizedQuerySet(
                queryset.model,
                using=queryset.db,
            ).for_user(user=user)

        return queryset.filter(
            pk__in=visible_queryset.using(queryset.db).values("pk"),
        )

    def get_queryset(self, request: Any) -> Any:
        """Return only objects visible through the request user's tenant scope."""
        queryset = super().get_queryset(request)
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            queryset = queryset.using(router.db_for_write(self.model))
        queryset = self._scope_queryset_for_user(queryset, user=request.user)
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            return tenant_role_access.scope_manageable_queryset(
                queryset,
                user=request.user,
            )
        return queryset

    def delete_model(self, request: Any, obj: Any) -> None:
        """Reject direct deletion when the object's membership role is read-only."""
        if not tenant_role_access.can_manage_object(
            user=getattr(request, "user", None),
            obj=obj,
        ):
            raise PermissionDenied
        super().delete_model(request, obj)

    def delete_queryset(self, request: Any, queryset: Any) -> None:
        """Reject mixed-role bulk deletes instead of partially applying them."""
        manageable = tenant_role_access.scope_manageable_queryset(
            queryset,
            user=getattr(request, "user", None),
        )
        if manageable.count() != queryset.count():
            raise PermissionDenied
        super().delete_queryset(request, manageable)

    def _scope_related_queryset(self, db_field: Any, request: Any, kwargs: dict[str, Any]) -> None:
        """Limit a relationship widget to tenant-visible target objects."""
        if not (micboard_settings.msp_enabled or micboard_settings.multi_site_mode):
            return

        related_model = db_field.remote_field.model
        related_label = getattr(getattr(related_model, "_meta", None), "label_lower", "")
        if related_label in SHARED_ADMIN_REFERENCE_MODEL_LABELS:
            return

        queryset = kwargs.get("queryset")
        if queryset is None:
            manager = related_model._default_manager
            database = kwargs.get("using")
            if database is not None:
                manager = manager.db_manager(database)
            queryset = manager.all()

        visible_queryset = self._scope_queryset_for_user(
            queryset,
            user=request.user,
        )
        kwargs["queryset"] = tenant_role_access.scope_manageable_queryset(
            visible_queryset,
            user=request.user,
        )

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        """Build a foreign-key widget without cross-tenant choices."""
        self._scope_related_queryset(db_field, request, kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(
        self,
        db_field: Any,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        """Build a many-to-many widget without cross-tenant choices."""
        self._scope_related_queryset(db_field, request, kwargs)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class TenantScopedAdminInlineMixin:
    """Apply the shared tenant boundary to editable inline relationships."""

    @staticmethod
    def _scope_queryset_for_user(queryset: Any, *, user: Any) -> Any:
        return MicboardModelAdmin._scope_queryset_for_user(queryset, user=user)

    def _scope_related_queryset(
        self,
        db_field: Any,
        request: Any,
        kwargs: dict[str, Any],
    ) -> None:
        MicboardModelAdmin._scope_related_queryset(self, db_field, request, kwargs)  # type: ignore[arg-type]

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        """Build an inline foreign-key widget without cross-tenant choices."""
        self._scope_related_queryset(db_field, request, kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)  # type: ignore[misc]

    def formfield_for_manytomany(
        self,
        db_field: Any,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        """Build an inline many-to-many widget without cross-tenant choices."""
        self._scope_related_queryset(db_field, request, kwargs)
        return super().formfield_for_manytomany(db_field, request, **kwargs)  # type: ignore[misc]
