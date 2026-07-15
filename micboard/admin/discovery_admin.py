"""Admin interfaces for device discovery management.

Provides admin views for DiscoveryQueue (device approval workflow) and
DeviceMovementLog (movement tracking and acknowledgment).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.discovery.queue import DeviceMovementLog, DiscoveryQueue

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(DiscoveryQueue)
class DiscoveryQueueAdmin(MicboardModelAdmin):
    """Admin interface for managing discovered devices awaiting review."""

    list_display = (
        "name",
        "manufacturer",
        "serial_number",
        "ip",
        "device_type",
        "status_badge",
        "conflict_indicators",
        "discovered_at",
    )
    list_filter = (
        "status",
        "manufacturer",
        "device_type",
        "is_duplicate",
        "is_ip_conflict",
        "discovered_at",
    )
    search_fields = (
        "name",
        "serial_number",
        "api_device_id",
        "ip",
    )
    readonly_fields = (
        "discovered_at",
        "reviewed_at",
        "reviewed_by",
        "existing_device",
        "existing_charger",
        "conflict_analysis",
    )
    list_select_related = ("manufacturer", "existing_device", "existing_charger")
    fieldsets = (
        (
            "Device Information",
            {
                "fields": (
                    "manufacturer",
                    "api_device_id",
                    "serial_number",
                    "name",
                    "fqdn",
                    "device_type",
                    "model",
                    "firmware_version",
                )
            },
        ),
        (
            "Network Information",
            {"fields": ("ip",)},
        ),
        (
            "Review Status",
            {
                "fields": (
                    "status",
                    "is_duplicate",
                    "is_ip_conflict",
                    "existing_device",
                    "existing_charger",
                    "notes",
                    "reviewed_at",
                    "reviewed_by",
                )
            },
        ),
        (
            "Discovery Details",
            {
                "fields": ("discovered_at", "metadata"),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["approve_devices", "reject_devices", "mark_as_duplicate"]

    @admin.display(description="Status")
    def status_badge(self, obj: DiscoveryQueue) -> str:
        """Display status as colored badge."""
        colors = {
            "pending": "orange",
            "approved": "green",
            "rejected": "red",
            "imported": "blue",
            "duplicate": "var(--body-quiet-color, gray)",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.status.upper(),
        )

    @admin.display(description="Conflicts")
    def conflict_indicators(self, obj: DiscoveryQueue) -> str:
        """Display warning badges for conflicts."""
        badges = []
        if obj.is_duplicate:
            badges.append(
                format_html(
                    '<span style="background-color: #ffcc00; color: black; padding: 3px 8px; '
                    'border-radius: 3px; font-weight: bold;">{}</span>',
                    "⚠ DUPLICATE",
                )
            )
        if obj.is_ip_conflict:
            badges.append(
                format_html(
                    '<span style="background-color: #ff3333; color: white; padding: 3px 8px; '
                    'border-radius: 3px; font-weight: bold;">{}</span>',
                    "⛔ IP CONFLICT",
                )
            )
        if obj.is_duplicate_api_id:
            badges.append(
                format_html(
                    '<span style="background-color: #ff6600; color: white; padding: 3px 8px; '
                    'border-radius: 3px; font-weight: bold;">🚨 {} API IDs</span>',
                    obj.api_id_conflict_count,
                )
            )
        return format_html_join(" ", "{}", ((badge,) for badge in badges)) if badges else "—"

    @admin.display(description="Conflict Analysis")
    def conflict_analysis(self, obj: DiscoveryQueue) -> str:
        """Display typed conflict details from the deduplication module."""
        from micboard.services.deduplication.queue_conflict_service import (
            DiscoveryQueueConflictService,
        )

        conflicts = DiscoveryQueueConflictService.check(obj)
        if not conflicts.has_conflict:
            return "✓ No conflicts detected"

        parts = [f"conflict_type: {conflicts.conflict_type}"]
        if conflicts.existing_device is not None:
            parts.append(f"existing_device: {conflicts.existing_device}")
        if conflicts.existing_charger is not None:
            parts.append(f"existing_charger: {conflicts.existing_charger}")
        return " | ".join(parts)

    @admin.action(permissions=["change"], description="Approve selected devices for import")
    def approve_devices(self, request: HttpRequest, queryset):
        """Delegate approval to the atomic discovery service."""
        from micboard.services.sync.discovery_approval_service import DiscoveryApprovalService

        try:
            result = DiscoveryApprovalService().approve(
                queryset=queryset,
                reviewer=request.user,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return

        messages.success(
            request,
            f"Approved and imported {result.imported_count} device(s).",
        )

    @admin.action(permissions=["change"], description="Reject selected devices")
    def reject_devices(self, request: HttpRequest, queryset):
        """Reject devices and prevent import."""
        count = queryset.filter(status="pending").update(
            status="rejected",
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
        )
        messages.success(request, f"Rejected {count} device(s).")

    @admin.action(permissions=["change"], description="Mark as duplicate (no import)")
    def mark_as_duplicate(self, request: HttpRequest, queryset):
        """Mark devices as duplicates without importing."""
        count = queryset.filter(status="pending").update(
            status="duplicate",
            is_duplicate=True,
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
        )
        messages.success(request, f"Marked {count} device(s) as duplicate.")


@admin.register(DeviceMovementLog)
class DeviceMovementLogAdmin(MicboardModelAdmin):
    """Admin interface for tracking and acknowledging device movements."""

    list_display = (
        "device_name",
        "manufacturer",
        "movement_summary",
        "detected_at",
        "acknowledged_badge",
    )
    list_filter = (
        "acknowledged",
        "device__manufacturer",
        "detected_at",
    )
    search_fields = (
        "device__name",
        "device__serial_number",
        "old_ip",
        "new_ip",
        "reason",
    )
    list_select_related = ("device", "device__manufacturer", "old_location", "new_location")
    readonly_fields = (
        "device",
        "old_ip",
        "new_ip",
        "old_location",
        "new_location",
        "detected_at",
        "detected_by",
        "reason",
        "movement_type_display",
    )
    fieldsets = (
        (
            "Device Information",
            {"fields": ("device",)},
        ),
        (
            "Movement Details",
            {
                "fields": (
                    "movement_type_display",
                    "old_ip",
                    "new_ip",
                    "old_location",
                    "new_location",
                    "reason",
                )
            },
        ),
        (
            "Detection",
            {
                "fields": (
                    "detected_at",
                    "detected_by",
                )
            },
        ),
        (
            "Acknowledgment",
            {
                "fields": (
                    "acknowledged",
                    "acknowledged_at",
                    "acknowledged_by",
                )
            },
        ),
    )
    actions = ["acknowledge_movements"]

    @admin.display(description="Device")
    def device_name(self, obj: DeviceMovementLog) -> str:
        """Display device name."""
        return obj.device.name or obj.device.api_device_id

    @admin.display(description="Manufacturer")
    def manufacturer(self, obj: DeviceMovementLog) -> str:
        """Display manufacturer name."""
        return obj.device.manufacturer.name

    @admin.display(description="Movement")
    def movement_summary(self, obj: DeviceMovementLog) -> str:
        """Display movement details as formatted text."""
        parts = []

        if obj.old_ip and obj.new_ip and obj.old_ip != obj.new_ip:
            parts.append(f"IP: {obj.old_ip} → {obj.new_ip}")

        if obj.old_location and obj.new_location and obj.old_location != obj.new_location:
            parts.append(f"Location: {obj.old_location.name} → {obj.new_location.name}")

        if not parts:
            return "No changes detected"

        return " | ".join(parts)

    @admin.display(description="Status")
    def acknowledged_badge(self, obj: DeviceMovementLog) -> str:
        """Display acknowledgment status as badge."""
        if obj.acknowledged:
            return format_html(
                '<span style="background-color: green; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-weight: bold;">{}</span>',
                "✓ ACKNOWLEDGED",
            )
        return format_html(
            '<span style="background-color: orange; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            "⚠ PENDING",
        )

    @admin.display(description="Movement Type")
    def movement_type_display(self, obj: DeviceMovementLog) -> str:
        """Display movement type with icon."""
        icons = {
            "ip_only": "🌐",
            "location_only": "📍",
            "ip_and_location": "🔀",
            "unknown": "❓",
        }
        icon = icons.get(obj.movement_type, "")
        return f"{icon} {obj.movement_type.replace('_', ' ').title()}"

    @admin.action(permissions=["change"], description="Acknowledge selected movements")
    def acknowledge_movements(self, request: HttpRequest, queryset):
        """Mark movements as acknowledged by admin."""
        count = queryset.filter(acknowledged=False).update(
            acknowledged=True,
            acknowledged_at=timezone.now(),
            acknowledged_by=request.user,
        )
        messages.success(request, f"Acknowledged {count} movement(s).")
