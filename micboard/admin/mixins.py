from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin

from micboard.utils.dependencies import (
    HAS_ADMIN_SORTABLE,
    HAS_IMPORT_EXPORT,
    HAS_RANGE_FILTER,
    HAS_SIMPLE_HISTORY,
)

logger = logging.getLogger(__name__)

# 1. Import-Export Support
if HAS_IMPORT_EXPORT:
    from import_export.admin import ImportExportModelAdmin as BaseImportExportAdmin
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

# 4. Range Filter Support
if HAS_RANGE_FILTER:
    from rangefilter.filters import DateRangeFilter, DateTimeRangeFilter
else:
    DateRangeFilter = admin.DateListFilter
    DateTimeRangeFilter = admin.DateListFilter


class EnhancedAdminMixin:
    """Combines optional admin improvements into a single mixin."""
    
    def get_list_filter(self, request: Any) -> list[Any]:
        """Upgrade date filters to range filters if available."""
        filters = list(super().get_list_filter(request))  # type: ignore
        if not HAS_RANGE_FILTER:
            return filters
            
        new_filters = []
        for f in filters:
            if f in ['created_at', 'updated_at', 'last_seen', 'timestamp', 'detected_at']:
                # Use range filter for timestamp fields
                new_filters.append((f, DateTimeRangeFilter))
            elif f in ['date', 'assigned_at']:
                new_filters.append((f, DateRangeFilter))
            else:
                new_filters.append(f)
        return new_filters


class MicboardModelAdmin(EnhancedAdminMixin, BaseImportExportAdmin, BaseHistoryAdmin, admin.ModelAdmin):
    """Base ModelAdmin for Micboard with all optional extras enabled."""
    pass


class MicboardSortableAdmin(BaseSortableAdmin, MicboardModelAdmin):
    """Sortable version of MicboardModelAdmin."""
    pass
