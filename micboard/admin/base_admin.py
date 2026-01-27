"""Base admin classes and mixins for django-micboard.

Consolidates common admin patterns:
- Status change actions (mark online, mark offline, etc.)
- Bulk operations (sync, approve, reject)
- List filters for common fields
- Custom admin change list displays
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin, messages
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class BaseHardwareAdmin(MicboardModelAdmin):
    """Base admin class for device models (Receiver, Transmitter, Charger).

    Provides common functionality:
    - Status filter (online/offline/degraded)
    - Manufacturer filter
    - Device type filter
    - Created/updated date filters
    - Read-only fields for audit trails
    - Custom list display with colored status badges
    """

    # Common list display fields
    list_display_fields: ClassVar[list[str]] = [
        "name",
        "status_badge",
        "manufacturer",
        "device_type",
        "last_synced",
    ]

    # Common list filters
    common_list_filters: ClassVar[list[str]] = [
        "status",
        "manufacturer",
        "device_type",
        "is_active",
        "created_at",
    ]

    # Read-only fields for audit
    readonly_fields_audit: ClassVar[list[str]] = [
        "created_at",
        "updated_at",
        "last_synced",
        "api_device_id",
    ]

    def get_list_display(self, request: HttpRequest) -> list[str]:
        """Get list display fields, can be overridden by subclasses."""
        return self.list_display_fields

    def get_list_filter(self, request: HttpRequest) -> Any:
        """Get list filter fields."""
        return self.common_list_filters

    @admin.display(description="Status")
    def status_badge(self, obj: Any) -> str:
        """Display colored status badge."""
        status = getattr(obj, "status", "unknown")
        colors = {
            "online": "#28a745",  # Green
            "offline": "#dc3545",  # Red
            "degraded": "#ffc107",  # Yellow
            "maintenance": "#17a2b8",  # Blue
            "unknown": "#6c757d",  # Gray
        }
        color = colors.get(status, colors["unknown"])
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px;">{}</span>',
            color,
            status.upper(),
        )


class AdminStatusActionsMixin:
    """Mixin providing common status change actions.

    Includes:
    - mark_online: Mark selected items as online
    - mark_offline: Mark selected items as offline
    - mark_degraded: Mark selected items as degraded
    - mark_maintenance: Mark selected items in maintenance mode
    """

    @admin.action(description="Mark selected as online")
    def mark_online(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark selected items as online."""
        updated = queryset.update(status="online")
        self.message_user(
            request,
            f"Marked {updated} item(s) as online.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark selected as offline")
    def mark_offline(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark selected items as offline."""
        updated = queryset.update(status="offline")
        self.message_user(
            request,
            f"Marked {updated} item(s) as offline.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark selected as degraded")
    def mark_degraded(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark selected items as degraded."""
        updated = queryset.update(status="degraded")
        self.message_user(
            request,
            f"Marked {updated} item(s) as degraded.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark selected as in maintenance")
    def mark_maintenance(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark selected items in maintenance mode."""
        updated = queryset.update(status="maintenance")
        self.message_user(
            request,
            f"Marked {updated} item(s) as in maintenance.",
            messages.SUCCESS,
        )


class AdminBulkActionsMixin:
    """Mixin providing common bulk operation actions.

    Includes:
    - enable: Mark selected items as active
    - disable: Mark selected items as inactive
    - delete_selected (Django default): Delete selected items
    """

    @admin.action(description="Enable selected items")
    def enable(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Enable (activate) selected items."""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Enabled {updated} item(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Disable selected items")
    def disable(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Disable (deactivate) selected items."""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Disabled {updated} item(s).",
            messages.SUCCESS,
        )


class AdminApprovalActionsMixin:
    """Mixin providing approval/rejection actions.

    Used for models with approval workflows (DiscoveryQueue, etc).

    Includes:
    - approve: Mark selected items as approved
    - reject: Mark selected items as rejected
    - reset_to_pending: Reset selected items to pending status
    """

    @admin.action(description="Approve selected items")
    def approve(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Approve selected items."""
        updated = queryset.update(status="approved")
        self.message_user(
            request,
            f"Approved {updated} item(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Reject selected items")
    def reject(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Reject selected items."""
        updated = queryset.update(status="rejected")
        self.message_user(
            request,
            f"Rejected {updated} item(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Reset selected to pending")
    def reset_to_pending(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Reset selected items to pending status."""
        updated = queryset.update(status="pending")
        self.message_user(
            request,
            f"Reset {updated} item(s) to pending.",
            messages.SUCCESS,
        )


class AdminListFilterMixin:
    """Mixin providing common list filter configurations.

    Consolidates filter definitions used across multiple admin classes.
    """

    # Status-based filters
    STATUS_FILTERS = ("status", "is_active")

    # Relationship filters
    MANUFACTURER_FILTERS = ("manufacturer",)

    # Device type filters
    HARDWARE_TYPE_FILTERS = ("device_type",)

    # Date filters
    DATE_FILTERS = ("created_at", "updated_at")

    # Combined common filters
    COMMON_FILTERS = STATUS_FILTERS + MANUFACTURER_FILTERS + DATE_FILTERS

    def get_list_filter(self, request: HttpRequest) -> tuple:
        """Get list filters. Can be overridden by subclasses.

        Returns:
            Tuple of filter field names
        """
        return self.COMMON_FILTERS


class AdminCustomColorMixin:
    """Mixin providing colored status display for admin list views.

    Consolidates status badge rendering with consistent colors.
    """

    # Status color mapping
    STATUS_COLORS = {
        "online": "#28a745",  # Green
        "offline": "#dc3545",  # Red
        "degraded": "#ffc107",  # Yellow
        "maintenance": "#17a2b8",  # Blue
        "pending": "#ffc107",  # Yellow
        "approved": "#28a745",  # Green
        "rejected": "#dc3545",  # Red
        "imported": "#28a745",  # Green
        "duplicate": "#6c757d",  # Gray
        "unknown": "#6c757d",  # Gray
    }

    def colored_status(self, obj: Any, field_name: str = "status") -> str:
        """Display colored status badge.

        Args:
            obj: Model instance
            field_name: Field to get status from

        Returns:
            HTML-formatted colored badge
        """
        status = getattr(obj, field_name, "unknown")
        color = self.STATUS_COLORS.get(status, self.STATUS_COLORS["unknown"])

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            status.upper(),
        )

    def colored_status_short_description(self, field_name: str = "status") -> str:
        """Get short description for colored status field."""
        return field_name.replace("_", " ").title()


class AdminAuditMixin:
    """Mixin providing audit field display and filtering.

    Shows created/updated timestamps and provides filtering by dates.
    """

    @admin.display(description="Created")
    def created_date_display(self, obj: Any) -> str:
        """Display created date."""
        created = getattr(obj, "created_at", None)
        return created.strftime("%Y-%m-%d %H:%M") if created else "N/A"

    @admin.display(description="Updated")
    def updated_date_display(self, obj: Any) -> str:
        """Display updated date."""
        updated = getattr(obj, "updated_at", None)
        return updated.strftime("%Y-%m-%d %H:%M") if updated else "N/A"

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        """Add audit fields to readonly."""
        readonly = list(super().get_readonly_fields(request, obj))  # type: ignore
        audit_fields = ["created_at", "updated_at", "created_date_display", "updated_date_display"]

        for field in audit_fields:
            if not any(field.startswith(f) for f in readonly):
                readonly.append(field)

        return readonly


# Convenience function to create a configured admin class
def create_hardware_admin(
    *,
    actions: list[str] | None = None,
    list_filters: list[str] | None = None,
    list_display: list[str] | None = None,
    include_status_actions: bool = True,
    include_bulk_actions: bool = False,
    include_approval_actions: bool = False,
) -> type:
    """Factory function to create a configured admin class.

    Args:
        actions: Additional actions to include
        list_filters: Custom list filters
        list_display: Custom list display
        include_status_actions: Include online/offline/degraded actions
        include_bulk_actions: Include enable/disable actions
        include_approval_actions: Include approve/reject actions

    Returns:
        Configured admin class
    """

    class ConfiguredHardwareAdmin(
        BaseHardwareAdmin,
        AdminCustomColorMixin,
        AdminAuditMixin,
    ):
        """Dynamically configured device admin."""

    if include_status_actions:
        if include_bulk_actions:
            if include_approval_actions:

                class DynamicAdminStatusBulkApproval(
                    AdminStatusActionsMixin,
                    AdminBulkActionsMixin,
                    AdminApprovalActionsMixin,
                ):
                    pass

                dynamic_admin = DynamicAdminStatusBulkApproval

            else:

                class DynamicAdminStatusBulk(
                    AdminStatusActionsMixin,
                    AdminBulkActionsMixin,
                ):
                    pass

                dynamic_admin = DynamicAdminStatusBulk

        elif include_approval_actions:

            class DynamicAdminStatusApproval(
                AdminStatusActionsMixin,
                AdminApprovalActionsMixin,
            ):
                pass

            dynamic_admin = DynamicAdminStatusApproval

        else:

            class DynamicAdminStatus(AdminStatusActionsMixin):
                pass

            dynamic_admin = DynamicAdminStatus

    else:

        class DynamicAdminEmpty:
            pass

        dynamic_admin = DynamicAdminEmpty

    # Apply mixins
    for base in dynamic_admin.__bases__:
        for attr_name in dir(base):
            if not attr_name.startswith("_"):
                attr = getattr(base, attr_name)
                if callable(attr) and hasattr(attr, "short_description"):
                    setattr(ConfiguredHardwareAdmin, attr_name, attr)

    # Set list display, filters, and actions
    if list_display:
        ConfiguredHardwareAdmin.list_display_fields = list_display
    if list_filters:
        ConfiguredHardwareAdmin.common_list_filters = list_filters

    actions_list = actions or []
    if include_status_actions:
        actions_list.extend(["mark_online", "mark_offline"])
    if include_bulk_actions:
        actions_list.extend(["enable", "disable"])
    if include_approval_actions:
        actions_list.extend(["approve", "reject"])

    if actions_list:
        ConfiguredHardwareAdmin.actions = actions_list

    return ConfiguredHardwareAdmin
