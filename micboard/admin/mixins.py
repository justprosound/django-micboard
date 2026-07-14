from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

from micboard.utils.dependencies import (
    HAS_ADMIN_SORTABLE,
    HAS_IMPORT_EXPORT,
    HAS_RANGE_FILTER,
    HAS_SIMPLE_HISTORY,
    HAS_UNFOLD,
)

logger = logging.getLogger(__name__)
_UNSET = object()

# Base ModelAdmin - Use Unfold if available
if HAS_UNFOLD:
    from unfold.admin import ModelAdmin as BaseAdmin
    from unfold.contrib.filters.admin import FieldTextFilter, RangeDateFilter, RangeDateTimeFilter
else:
    from django.contrib.admin import ModelAdmin as BaseAdmin

    FieldTextFilter = None
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


if HAS_IMPORT_EXPORT and HAS_UNFOLD:
    try:
        from unfold.contrib.import_export.forms import ExportForm, ImportForm

        BaseImportExportAdmin.import_form_class = ImportForm
        BaseImportExportAdmin.export_form_class = ExportForm
    except ImportError:
        logger.debug("Unfold import-export forms are unavailable")


# 2. Sortable Support
if HAS_ADMIN_SORTABLE:
    from adminsortable2.admin import SortableAdminMixin as BaseSortableAdmin
else:

    class BaseSortableAdmin:  # type: ignore
        pass


# 3. Simple History Support
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
        if HAS_UNFOLD:
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

    @staticmethod
    def _scope_queryset_for_user(queryset: Any, *, user: Any) -> Any:
        """Intersect a queryset with the user's active tenant memberships.

        Models with a tenant-aware manager remain the source of truth. Standard
        managers use the same tenant lookup contract; models without a safe
        tenant path fail closed while MSP mode is enabled.
        """
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return queryset
        if user.is_superuser and getattr(settings, "MICBOARD_ALLOW_CROSS_ORG_VIEW", True):
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
        return self._scope_queryset_for_user(queryset, user=request.user)

    def _scope_related_queryset(self, db_field: Any, request: Any, kwargs: dict[str, Any]) -> None:
        """Limit a relationship widget to tenant-visible target objects."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return

        queryset = kwargs.get("queryset")
        if queryset is None:
            related_model = db_field.remote_field.model
            manager = related_model._default_manager
            database = kwargs.get("using")
            if database is not None:
                manager = manager.db_manager(database)
            queryset = manager.all()

        kwargs["queryset"] = self._scope_queryset_for_user(
            queryset,
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


class MicboardSortableAdmin(BaseSortableAdmin, MicboardModelAdmin):
    """Sortable version of MicboardModelAdmin."""

    _change_list_template_override: Any = _UNSET

    @property
    def change_list_template(self) -> Any:
        """Compose admin-sortable's base template with import-export's override."""
        if self._change_list_template_override is not _UNSET:
            return self._change_list_template_override
        return super().change_list_template  # type: ignore[misc]

    @change_list_template.setter
    def change_list_template(self, value: Any) -> None:
        self._change_list_template_override = value

    if HAS_UNFOLD and HAS_ADMIN_SORTABLE:
        # Override templates to use Unfold compatible ones if needed,
        # or at least ensure we don't crash when adminsortable2
        # looks for its own templates.
        # Actually, adminsortable2 often works if we just let Unfold
        # take over the rendering but keep the mixin logic.
        pass
