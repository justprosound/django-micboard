from __future__ import annotations

import logging
from typing import Any

from micboard.utils.dependencies import (
    HAS_ADMIN_SORTABLE,
    HAS_IMPORT_EXPORT,
    HAS_RANGE_FILTER,
    HAS_SIMPLE_HISTORY,
    HAS_UNFOLD,
)

logger = logging.getLogger(__name__)

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
if HAS_IMPORT_EXPORT:
    from import_export.admin import ImportExportModelAdmin as DjangoImportExportAdmin

    if HAS_UNFOLD:
        try:
            from unfold.contrib.import_export.forms import ExportForm, ImportForm

            class BaseImportExportAdmin(DjangoImportExportAdmin):
                import_form_class = ImportForm
                export_form_class = ExportForm
        except ImportError:

            class BaseImportExportAdmin(DjangoImportExportAdmin):
                pass
    else:

        class BaseImportExportAdmin(DjangoImportExportAdmin):
            pass
else:

    class BaseImportExportAdmin:  # type: ignore
        pass


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
            new_filters = []
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

        new_filters = []
        for f in filters:
            if f in ["created_at", "updated_at", "last_seen", "timestamp", "detected_at"]:
                new_filters.append((f, DateTimeRangeFilter))
            elif f in ["date", "assigned_at"]:
                new_filters.append((f, DateRangeFilter))
            else:
                new_filters.append(f)
        return new_filters


class MicboardModelAdmin(EnhancedAdminMixin, BaseImportExportAdmin, BaseHistoryAdmin, BaseAdmin):
    """Base ModelAdmin for Micboard with all optional extras enabled."""

    # Unfold specific default settings
    list_filter_submit = HAS_UNFOLD
    list_fullwidth = HAS_UNFOLD
    warn_unsaved_form = HAS_UNFOLD


class MicboardSortableAdmin(BaseSortableAdmin, MicboardModelAdmin):
    """Sortable version of MicboardModelAdmin."""

    if HAS_UNFOLD and HAS_ADMIN_SORTABLE:
        # Override templates to use Unfold compatible ones if needed,
        # or at least ensure we don't crash when adminsortable2
        # looks for its own templates.
        # Actually, adminsortable2 often works if we just let Unfold
        # take over the rendering but keep the mixin logic.
        pass
