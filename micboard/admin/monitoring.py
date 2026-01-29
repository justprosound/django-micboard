"""Admin configuration for monitoring models.

(Location, MonitoringGroup, Config, DiscoveredDevice).

This module provides Django admin interfaces for managing monitoring groups,
locations, and system configuration.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import DiscoveredDevice, Location, MicboardConfig, MonitoringGroup

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
        protocol = obj.get_communication_protocol()
        if protocol:
            return protocol
        return "—"

    @admin.display(description="Managed", boolean=True)
    def is_managed_display(self, obj):
        """Check if this discovered device is already managed as a chassis."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(
            ip=obj.ip,
            manufacturer=obj.manufacturer,
        ).exists()

    @admin.display(description="Manageable", boolean=True)
    def is_manageable_display(self, obj):
        """Check if device can be managed via API."""
        return obj.is_manageable()

    @admin.display(description="Manageability Status")
    def manageable_status_detail(self, obj):
        """Display detailed status about whether device can be managed."""
        if obj.is_manageable():
            return "✅ Device is ready to be managed and can be promoted to WirelessChassis"

        reason = obj.get_incompatibility_reason()
        if reason:
            return f"⚠️ Device cannot be managed: {reason}"

        can_promote, promotion_reason = obj.can_promote_to_chassis()
        if not can_promote:
            return f"ℹ️ Cannot promote: {promotion_reason}"

        return "Status unknown"

    @admin.display(description="Actions")
    def promotion_actions(self, obj):
        """Display promotion action buttons with status awareness."""
        from micboard.models import WirelessChassis

        is_managed = WirelessChassis.objects.filter(
            ip=obj.ip,
            manufacturer=obj.manufacturer,
        ).exists()

        if is_managed:
            return "✓ Already Managed"

        # Check if device can be promoted
        can_promote, reason = obj.can_promote_to_chassis()

        if not can_promote:
            return f"⛔ Cannot Promote ({reason})"

        if not obj.is_manageable():
            return "⚠️ Not Ready (device not ready for management)"

        return format_html(
            '<a class="button" href="{}">✅ Promote to Chassis</a>',
            f"/admin/micboard/discovereddevice/{obj.pk}/promote/",
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

    def promote_device_view(self, request, pk):
        """Promote a discovered device to a managed WirelessChassis."""
        try:
            discovered = DiscoveredDevice.objects.get(pk=pk)
        except DiscoveredDevice.DoesNotExist:
            messages.error(request, "Discovered device not found.")
            return redirect("..")

        # Call the promotion service
        success, message, chassis = self._promote_to_chassis(discovered)

        if success:
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
        from micboard.services.plugin_registry import PluginRegistry

        updated_count = 0
        failed_count = 0

        for discovered in queryset:
            if not discovered.manufacturer:
                failed_count += 1
                continue

            try:
                plugin = PluginRegistry.get_plugin(
                    discovered.manufacturer.code, discovered.manufacturer
                )
                if not plugin:
                    failed_count += 1
                    continue

                # Fetch fresh device list
                api_devices = plugin.get_devices() or []

                # Find matching device by IP or device ID
                device_data = None
                for dev in api_devices:
                    if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                        device_data = dev
                        break
                    if discovered.api_device_id and dev.get("id") == discovered.api_device_id:
                        device_data = dev
                        break

                if device_data:
                    # Update discovered device with fresh data
                    discovered.device_state = device_data.get("state", "UNKNOWN")
                    discovered.compatibility = device_data.get("compatibility", "UNKNOWN")
                    discovered.model = device_data.get("model", discovered.model)
                    discovered.api_device_id = device_data.get("id", discovered.api_device_id)

                    # Extract communication protocol
                    comm_protocol = device_data.get("communicationProtocol", {})
                    if isinstance(comm_protocol, dict):
                        discovered.communication_protocol = comm_protocol.get("name", "")

                    discovered.save()
                    updated_count += 1
                else:
                    failed_count += 1
                    logger.warning("Could not find device %s in API response", discovered.ip)

            except Exception as e:
                failed_count += 1
                logger.exception("Failed to refresh discovered device %s: %s", discovered.ip, e)

        if updated_count > 0:
            messages.success(
                request,
                f"✅ Refreshed {updated_count} device(s) from manufacturer API.",
            )
        if failed_count > 0:
            messages.warning(
                request,
                f"⚠️ {failed_count} device(s) could not be refreshed. Check logs for details.",
            )

    @admin.action(description="Promote selected devices to managed chassis")
    def promote_to_chassis_action(self, request, queryset):
        """Bulk action to promote discovered devices to WirelessChassis."""
        promoted_count = 0
        failed_count = 0

        for discovered in queryset:
            success, message, chassis = self._promote_to_chassis(discovered)
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

    @admin.action(description="Delete and remove from manufacturer API discovery list")
    def delete_and_remove_from_api(self, request, queryset):
        """Delete discovered devices and remove from remote API discovery lists."""
        from micboard.services.plugin_registry import PluginRegistry

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
                    logger.warning(
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

    def _promote_to_chassis(self, discovered: DiscoveredDevice) -> tuple[bool, str, object]:
        """Promote a discovered device to a managed WirelessChassis.

        Returns:
            Tuple of (success: bool, message: str, chassis: WirelessChassis | None)
        """
        from micboard.models import WirelessChassis
        from micboard.services.hardware_deduplication_service import (
            get_hardware_deduplication_service,
        )

        if not discovered.manufacturer:
            return (False, "No manufacturer specified for discovered device", None)

        # Check if already managed
        existing = WirelessChassis.objects.filter(
            ip=discovered.ip,
            manufacturer=discovered.manufacturer,
        ).first()

        if existing:
            return (False, f"Device already managed as chassis: {existing}", existing)

        # Fetch fresh data from API to ensure we have complete device info
        try:
            from micboard.services.plugin_registry import PluginRegistry

            plugin = PluginRegistry.get_plugin(
                discovered.manufacturer.code, discovered.manufacturer
            )
            if not plugin:
                return (False, "Plugin not available for manufacturer", None)

            # Try to get detailed device data from API using the IP
            api_devices = plugin.get_devices() or []
            device_data = None

            for dev in api_devices:
                if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                    device_data = dev
                    break

            if not device_data:
                # Fallback: create basic chassis from discovered data
                logger.warning(
                    "Could not fetch detailed data for %s from API, creating basic chassis",
                    discovered.ip,
                )
                chassis = WirelessChassis.objects.create(
                    manufacturer=discovered.manufacturer,
                    api_device_id=discovered.ip,  # Use IP as fallback ID
                    ip=discovered.ip,
                    name=f"{discovered.device_type} at {discovered.ip}",
                    model=discovered.device_type,
                    role="receiver",  # Default role
                    max_channels=discovered.channels or 4,
                    status="discovered",
                )
                return (True, "Created basic chassis (limited API data)", chassis)

            # Use full sync path with deduplication
            from micboard.services.manufacturer import ManufacturerService

            # Transform device data
            transformed = plugin.transform_device_data(device_data)
            if not transformed:
                return (False, "Failed to transform device data", None)

            # Get deduplication service
            dedup_service = get_hardware_deduplication_service(discovered.manufacturer)

            # Check for conflicts
            dedup_result = dedup_service.check_device(
                serial_number=transformed.get("serial_number"),
                mac_address=transformed.get("mac_address"),
                ip=transformed.get("ip"),
                api_device_id=transformed.get("api_device_id"),
                manufacturer=discovered.manufacturer,
            )

            if dedup_result.is_conflict:
                return (
                    False,
                    f"Device conflict: {dedup_result.conflict_reason}",
                    None,
                )

            if dedup_result.is_duplicate and dedup_result.existing_device:
                # Update existing device
                chassis = dedup_result.existing_device
                ManufacturerService._update_existing_chassis(
                    chassis,
                    ManufacturerService._normalize_devices([device_data], plugin)[0],
                )
                return (True, "Updated existing chassis", chassis)

            # Create new chassis
            normalized = ManufacturerService._normalize_devices([device_data], plugin)
            if normalized:
                chassis = ManufacturerService._create_chassis(
                    normalized[0],
                    discovered.manufacturer,
                )
                return (True, "Created new managed chassis", chassis)

            return (False, "Failed to normalize device data", None)

        except Exception as e:
            logger.exception("Error promoting discovered device %s", discovered.ip)
            return (False, f"Exception during promotion: {e}", None)


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
