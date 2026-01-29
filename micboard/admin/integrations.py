"""Admin interfaces for integration and accessory management."""

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.integrations import Accessory, ManufacturerAPIServer


@admin.register(ManufacturerAPIServer)
class ManufacturerAPIServerAdmin(MicboardModelAdmin):
    """Admin interface for managing manufacturer API servers."""

    list_display = (
        "name",
        "status_indicator",
        "manufacturer_with_location",
        "health_check_status",
        "enabled_badge",
    )
    list_filter = ("manufacturer", "enabled", "status")
    search_fields = ("name", "base_url", "location_name")
    readonly_fields = ("created_at", "updated_at", "last_health_check", "status_message")

    fieldsets = (
        (
            "Server Identity",
            {
                "fields": ("name", "manufacturer", "location_name", "notes"),
            },
        ),
        (
            "Connection",
            {
                "fields": ("base_url", "shared_key", "verify_ssl"),
            },
        ),
        (
            "Status",
            {
                "fields": ("enabled", "status", "status_message", "last_health_check"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["test_connection", "enable_servers", "disable_servers"]

    @admin.display(description="Status")
    def status_indicator(self, obj: ManufacturerAPIServer) -> str:
        """Show color-coded status indicator."""
        colors = {
            ManufacturerAPIServer.Status.ACTIVE: "green",
            ManufacturerAPIServer.Status.INACTIVE: "gray",
            ManufacturerAPIServer.Status.ERROR: "red",
            ManufacturerAPIServer.Status.UNKNOWN: "orange",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {};">● {}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Manufacturer & Location")
    def manufacturer_with_location(self, obj: ManufacturerAPIServer) -> str:
        """Show manufacturer and location."""
        location = f"({obj.location_name})" if obj.location_name else "(No location)"
        return f"{obj.get_manufacturer_display()} {location}"

    @admin.display(description="Last Health Check")
    def health_check_status(self, obj: ManufacturerAPIServer) -> str:
        """Show when health check was last performed."""
        if obj.last_health_check:
            return obj.last_health_check.strftime("%Y-%m-%d %H:%M")
        return "Never tested"

    @admin.display(description="Enabled", boolean=True)
    def enabled_badge(self, obj: ManufacturerAPIServer) -> bool:
        """Show enabled/disabled status."""
        return obj.enabled

    @admin.action(description="🔍 Test connection to API servers")
    def test_connection(self, request: Any, queryset: QuerySet) -> None:
        """Test connection to selected API servers."""
        from micboard.integrations.shure.client import ShureSystemAPIClient

        for server in queryset:
            try:
                if server.manufacturer == "shure":
                    client = ShureSystemAPIClient(
                        base_url=server.base_url, verify_ssl=server.verify_ssl
                    )
                    # Try a simple health check
                    devices = client.discovery.get_devices()
                    server.status = ManufacturerAPIServer.Status.ACTIVE
                    server.status_message = (
                        f"✓ Connection successful ({len(devices)} devices found)"
                    )
                    server.last_health_check = now()
                else:
                    server.status = ManufacturerAPIServer.Status.UNKNOWN
                    server.status_message = (
                        f"Health check not implemented for {server.manufacturer}"
                    )
            except Exception as e:
                server.status = ManufacturerAPIServer.Status.ERROR
                server.status_message = f"✗ Connection failed: {str(e)[:200]}"
                server.last_health_check = now()
            server.save()

        self.message_user(
            request, f"Health check completed for {queryset.count()} server(s)", messages.SUCCESS
        )

    @admin.action(description="✓ Enable selected servers")
    def enable_servers(self, request: Any, queryset: QuerySet) -> None:
        """Enable selected servers."""
        count = queryset.update(enabled=True)
        self.message_user(request, f"{count} server(s) enabled", messages.SUCCESS)

    @admin.action(description="✗ Disable selected servers")
    def disable_servers(self, request: Any, queryset: QuerySet) -> None:
        """Disable selected servers."""
        count = queryset.update(enabled=False)
        self.message_user(request, f"{count} server(s) disabled", messages.WARNING)


class AccessoryAdmin(MicboardModelAdmin):
    """Admin interface for managing accessories."""

    list_display = (
        "name",
        "category_badge",
        "chassis_link",
        "assigned_to",
        "availability_status",
        "condition_badge",
    )
    list_filter = ("category", "condition", "is_available", "chassis__model", "chassis")
    search_fields = ("name", "serial_number", "assigned_to", "chassis__serial_number")
    list_select_related = ("chassis",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Accessory Details",
            {
                "fields": ("name", "sku", "category", "serial_number"),
            },
        ),
        (
            "Assignment",
            {
                "fields": ("chassis", "assigned_to"),
            },
        ),
        (
            "Condition & Availability",
            {
                "fields": ("condition", "is_available", "notes"),
            },
        ),
        (
            "Checkout History",
            {
                "fields": ("checked_out_date", "checked_in_date"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_available", "mark_unavailable", "mark_needs_repair", "update_checkout_status"]

    @admin.display(description="Category")
    def category_badge(self, obj: Accessory) -> str:
        """Show category as badge."""
        return obj.get_category_display()

    @admin.display(description="Chassis")
    def chassis_link(self, obj: Accessory) -> str:
        """Link to the chassis this accessory is assigned to."""
        url = reverse("admin:hardware_wirelesschassis_change", args=[obj.chassis.id])
        return format_html('<a href="{}">{}</a>', url, obj.chassis)

    @admin.display(description="Availability", boolean=True)
    def availability_status(self, obj: Accessory) -> bool:
        """Show availability status."""
        return obj.is_available

    @admin.display(description="Condition")
    def condition_badge(self, obj: Accessory) -> str:
        """Show condition as badge."""
        return obj.get_condition_display()

    @admin.action(description="✓ Mark as available")
    def mark_available(self, request: Any, queryset: QuerySet) -> None:
        """Mark accessories as available."""
        count = queryset.update(is_available=True)
        self.message_user(request, f"{count} accessory(ies) marked as available", messages.SUCCESS)

    @admin.action(description="✗ Mark as unavailable")
    def mark_unavailable(self, request: Any, queryset: QuerySet) -> None:
        """Mark accessories as unavailable."""
        count = queryset.update(is_available=False)
        self.message_user(
            request, f"{count} accessory(ies) marked as unavailable", messages.WARNING
        )

    @admin.action(description="⚠️ Mark as needs repair")
    def mark_needs_repair(self, request: Any, queryset: QuerySet) -> None:
        """Mark accessories as needing repair."""
        count = queryset.update(condition="needs_repair", is_available=False)
        self.message_user(
            request, f"{count} accessory(ies) marked as needing repair", messages.WARNING
        )

    @admin.action(description="📅 Update checkout dates")
    def update_checkout_status(self, request: Any, queryset: QuerySet) -> None:
        """Update checkout/checkin timestamps."""
        # This would open a form to bulk update dates
        self.message_user(request, "Use individual edit to update checkout dates", messages.INFO)
