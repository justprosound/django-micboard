"""Admin configuration for monitoring models.

(Location, MonitoringGroup, Config, DiscoveredDevice).

This module provides Django admin interfaces for managing monitoring groups,
locations, and system configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.discovery.registry import DiscoveredDevice, MicboardConfig
from micboard.models.locations.structure import Location
from micboard.models.monitoring.group import MonitoringGroup
from micboard.services.sync.discovered_device_service import (
    can_promote_device_to_chassis,
    get_device_communication_protocol,
    get_device_incompatibility_reason,
    is_device_manageable,
)

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


@admin.register(MicboardConfig)
class MicboardConfigAdmin(MicboardModelAdmin):
    """Admin configuration for MicboardConfig model."""

    list_display = ("key", "value")
    search_fields = ("key",)


@admin.register(DiscoveredDevice)
class DiscoveredDeviceAdmin(MicboardModelAdmin):
    """Admin configuration for DiscoveredDevice model with promotion workflow.

    Discovered devices are intermediate storage for devices found via API
    but not yet converted to managed WirelessChassis instances. This admin
    provides tools to review and promote discovered devices.
    """

    list_display = (
        "ip",
        "device_type",
        "model",
        "status_display_with_color",
        "protocol_display",
        "manufacturer",
        "channels",
        "discovered_at",
        "is_managed_display",
        "is_manageable_display",
        "promotion_actions",
    )
    list_filter = (
        "status",
        "manufacturer",
        "discovered_at",
    )
    search_fields = ("ip", "device_type", "model", "api_device_id", "notes")
    readonly_fields = ("discovered_at", "last_updated", "manageable_status_detail")
    fieldsets = (
        (
            "Device Identification",
            {
                "fields": (
                    "ip",
                    "api_device_id",
                    "device_type",
                    "model",
                    "manufacturer",
                    "channels",
                )
            },
        ),
        (
            "Status & Metadata",
            {
                "fields": (
                    "status",
                    "metadata",
                    "manageable_status_detail",
                ),
                "description": (
                    "Status shows the device's readiness for management. "
                    "Metadata contains manufacturer-specific data (compatibility, deviceState, etc.)."
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("discovered_at", "last_updated", "notes"),
                "classes": ("collapse",),
            },
        ),
    )
    actions: ClassVar[list[str]] = [
        "promote_to_chassis_action",
        "delete_and_remove_from_api",
        "refresh_from_api",
    ]

    def get_queryset(self, request):
        """Optimize queryset with related lookups."""
        qs = super().get_queryset(request)
        return qs.select_related("manufacturer")

    @admin.display(description="Status", ordering="status")
    def status_display_with_color(self, obj):
        """Display generic status with visual indicators."""
        status_map = {
            obj.STATUS_READY: ("✅ Ready", "var(--success-fg, green)", True),
            obj.STATUS_PENDING: ("🔍 Pending", "var(--warning-fg, orange)", False),
            obj.STATUS_INCOMPATIBLE: ("⚠️ Incompatible", "var(--error-fg, red)", True),
            obj.STATUS_ERROR: ("✕ Error", "var(--error-fg, red)", False),
            obj.STATUS_OFFLINE: ("📴 Offline", "var(--body-quiet-color, gray)", False),
        }

        if obj.status in status_map:
            text, color, bold = status_map[obj.status]
            weight = "bold" if bold else "normal"
            return format_html(
                '<span style="color: {}; font-weight: {};">{}</span>', color, weight, text
            )
        return obj.get_status_display()

    @admin.display(description="Protocol")
    def protocol_display(self, obj):
        """Display communication protocol from metadata."""
        protocol = get_device_communication_protocol(obj)
        if protocol:
            return protocol
        return "—"

    @admin.display(description="Managed", boolean=True)
    def is_managed_display(self, obj):
        """Check if this discovered device is already managed as a chassis."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        return WirelessChassis.objects.filter(
            ip=obj.ip,
            manufacturer=obj.manufacturer,
        ).exists()

    @admin.display(description="Manageable", boolean=True)
    def is_manageable_display(self, obj):
        """Check if device can be managed via API."""
        return is_device_manageable(obj)

    @admin.display(description="Manageability Status")
    def manageable_status_detail(self, obj):
        """Display detailed status about whether device can be managed."""
        if is_device_manageable(obj):
            return "✅ Device is ready to be managed and can be promoted to WirelessChassis"

        reason = get_device_incompatibility_reason(obj)
        if reason:
            return f"⚠️ Device cannot be managed: {reason}"

        can_promote, promotion_reason = can_promote_device_to_chassis(obj)
        if not can_promote:
            return f"Cannot promote: {promotion_reason}"

        return "Status unknown"

    @admin.display(description="Actions")
    def promotion_actions(self, obj):
        """Display promotion action buttons with status awareness."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        is_managed = WirelessChassis.objects.filter(
            ip=obj.ip,
            manufacturer=obj.manufacturer,
        ).exists()

        if is_managed:
            return "✓ Already Managed"

        # Check if device can be promoted
        can_promote, reason = can_promote_device_to_chassis(obj)

        if not can_promote:
            return f"⛔ Cannot Promote ({reason})"

        if not is_device_manageable(obj):
            return "⚠️ Not Ready (device not ready for management)"

        return format_html(
            '<button type="submit" class="button" formmethod="post" formaction="{}">'
            "✅ Promote to Chassis</button>",
            reverse("admin:micboard_discoverdevice_promote", args=[obj.pk]),
        )

    def get_urls(self):
        """Add custom URL for promotion workflow."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:pk>/promote/",
                self.admin_site.admin_view(self.promote_device_view),
                name="micboard_discoverdevice_promote",
            ),
        ]
        return custom_urls + urls

    @method_decorator(require_POST)
    def promote_device_view(self, request, pk):
        """Promote a discovered device to a managed WirelessChassis."""
        try:
            discovered = DiscoveredDevice.objects.get(pk=pk)
        except DiscoveredDevice.DoesNotExist:
            messages.error(request, "Discovered device not found.")
            return redirect("..")

        if not self._has_promotion_permission(request, discovered):
            raise PermissionDenied

        # Call the promotion service
        success, message, chassis = self._promote_to_chassis(discovered)

        if success and chassis is not None:
            messages.success(
                request,
                f"✅ Successfully promoted {discovered.ip} to managed chassis: {chassis}",
            )
            # Optionally delete the discovered device entry
            discovered.delete()
            return redirect(f"/admin/micboard/wirelesschassis/{chassis.pk}/change/")
        else:
            messages.error(request, f"❌ Failed to promote device: {message}")
            return redirect("..")

    @admin.action(description="Refresh device data from manufacturer API")
    def refresh_from_api(self, request, queryset):
        """Refresh discovered device data from manufacturer API."""
        from micboard.services.sync.device_refresh_service import DeviceRefreshService

        service = DeviceRefreshService()
        updated, failed = service.refresh_discovered_devices_from_api(queryset)

        if updated > 0:
            messages.success(
                request,
                f"✅ Refreshed {updated} device(s) from manufacturer API.",
            )
        if failed > 0:
            messages.warning(
                request,
                f"⚠️ {failed} device(s) could not be refreshed. Check logs for details.",
            )

    @admin.action(description="Promote selected devices to managed chassis")
    def promote_to_chassis_action(self, request, queryset):
        """Bulk action to promote discovered devices to WirelessChassis."""
        if not self._has_promotion_permission(request):
            raise PermissionDenied

        promoted_count = 0
        failed_count = 0

        for discovered in queryset:
            success, message, _chassis = self._promote_to_chassis(discovered)
            if success:
                promoted_count += 1
                discovered.delete()  # Clean up after promotion
            else:
                failed_count += 1
                logger.warning(
                    "Failed to promote discovered device %s: %s",
                    discovered.ip,
                    message,
                )

        if promoted_count > 0:
            messages.success(
                request,
                f"✅ Successfully promoted {promoted_count} device(s) to managed chassis.",
            )
        if failed_count > 0:
            messages.warning(
                request,
                f"⚠️ Failed to promote {failed_count} device(s). Check logs for details.",
            )

    @admin.action(
        permissions=["delete"],
        description="Delete and remove from manufacturer API discovery list",
    )
    def delete_and_remove_from_api(self, request, queryset):
        """Delete discovered devices and remove from remote API discovery lists."""
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        removed_count = 0
        failed_count = 0

        for discovered in queryset:
            # Try to remove from manufacturer's discovery list
            if discovered.manufacturer:
                try:
                    plugin = PluginRegistry.get_plugin(
                        discovered.manufacturer.code, discovered.manufacturer
                    )

                    if plugin and hasattr(plugin, "remove_discovery_ips"):
                        plugin.remove_discovery_ips([discovered.ip])
                except Exception as e:
                    logger.exception(
                        "Failed to remove IP %s from discovery list: %s",
                        discovered.ip,
                        e,
                    )
                    failed_count += 1

            # Delete the discovered device record
            discovered.delete()
            removed_count += 1

        messages.success(
            request,
            f"✅ Deleted {removed_count} discovered device(s) and removed from API discovery lists.",
        )
        if failed_count > 0:
            messages.warning(
                request,
                f"⚠️ {failed_count} device(s) could not be removed from API discovery lists.",
            )

    def _promote_to_chassis(
        self, discovered: DiscoveredDevice
    ) -> tuple[bool, str, WirelessChassis | None]:
        """Delegate promotion to DevicePromotionService to keep admin thin and testable."""
        from micboard.services.sync.device_promotion_service import DevicePromotionService

        service = DevicePromotionService()
        return service.promote_discovered_device(discovered)

    def _has_promotion_permission(self, request, obj=None) -> bool:
        """Require every permission needed by the promotion transaction."""
        return (
            self.has_change_permission(request, obj)
            and self.has_delete_permission(request, obj)
            and request.user.has_perm("micboard.add_wirelesschassis")
        )


@admin.register(Location)
class LocationAdmin(MicboardModelAdmin):
    """Admin configuration for Location model."""

    list_display = ("name", "building", "room")
    list_filter = ("building", "room")
    search_fields = ("name", "building", "room")
    list_select_related = ("building", "room")


@admin.register(MonitoringGroup)
class MonitoringGroupAdmin(MicboardModelAdmin):
    """Admin configuration for MonitoringGroup model."""

    list_display = ("name", "is_active")
    list_filter = ()
    search_fields = ("name", "description")
    filter_horizontal = (
        "users",
        "channels",
    )  # Use filter_horizontal for better UX with many-to-many
