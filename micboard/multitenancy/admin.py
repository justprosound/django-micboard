"""Admin interface for multi-tenancy models.

Provides organization and campus management in Django admin.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin

# Only register admin if MSP enabled
if getattr(settings, "MICBOARD_MSP_ENABLED", False):
    from .models import Campus, Organization, OrganizationMembership

    @admin.register(Organization)
    class OrganizationAdmin(admin.ModelAdmin):
        """Admin interface for Organization model."""

        list_display = [
            "name",
            "slug",
            "site",
            "subscription_tier",
            "is_active",
            "max_devices",
            "device_count",
            "created_at",
        ]
        list_filter = ["is_active", "subscription_tier", "site", "created_at"]
        search_fields = ["name", "slug"]
        prepopulated_fields = {"slug": ("name",)}
        readonly_fields = ["created_at", "updated_at", "device_count"]
        fieldsets = [
            (
                "Basic Information",
                {
                    "fields": [
                        "name",
                        "slug",
                        "site",
                        "is_active",
                        "primary_contact",
                    ]
                },
            ),
            (
                "Subscription & Limits",
                {
                    "fields": [
                        "subscription_tier",
                        "max_devices",
                    ]
                },
            ),
            (
                "Branding",
                {
                    "fields": ["logo", "primary_color"],
                    "classes": ["collapse"],
                },
            ),
            (
                "Metadata",
                {
                    "fields": ["created_at", "updated_at", "device_count"],
                    "classes": ["collapse"],
                },
            ),
        ]

        @admin.display(description="Current Devices")
        def device_count(self, obj: Organization) -> int:
            """Display current device count."""
            return obj.get_device_count()

    @admin.register(Campus)
    class CampusAdmin(admin.ModelAdmin):
        """Admin interface for Campus model."""

        list_display = [
            "name",
            "organization",
            "city",
            "state",
            "is_active",
            "created_at",
        ]
        list_filter = ["is_active", "organization", "state", "created_at"]
        search_fields = ["name", "slug", "address", "city"]
        prepopulated_fields = {"slug": ("name",)}
        readonly_fields = ["created_at", "updated_at"]
        fieldsets = [
            (
                "Basic Information",
                {
                    "fields": [
                        "organization",
                        "name",
                        "slug",
                        "is_active",
                    ]
                },
            ),
            (
                "Location Details",
                {
                    "fields": [
                        "address",
                        "city",
                        "state",
                        "postal_code",
                        "country",
                        "timezone",
                    ]
                },
            ),
            (
                "Notes",
                {
                    "fields": ["notes"],
                    "classes": ["collapse"],
                },
            ),
            (
                "Metadata",
                {
                    "fields": ["created_at", "updated_at"],
                    "classes": ["collapse"],
                },
            ),
        ]

    @admin.register(OrganizationMembership)
    class OrganizationMembershipAdmin(admin.ModelAdmin):
        """Admin interface for OrganizationMembership model."""

        list_display = [
            "user",
            "organization",
            "campus",
            "role",
            "is_active",
            "created_at",
        ]
        list_filter = ["is_active", "role", "organization", "created_at"]
        search_fields = [
            "user__username",
            "user__email",
            "organization__name",
            "campus__name",
        ]
        readonly_fields = ["created_at", "updated_at"]
        autocomplete_fields = ["user", "organization", "campus"]
        fieldsets = [
            (
                "Membership",
                {
                    "fields": [
                        "user",
                        "organization",
                        "campus",
                        "role",
                        "is_active",
                    ]
                },
            ),
            (
                "Metadata",
                {
                    "fields": ["created_by", "created_at", "updated_at"],
                    "classes": ["collapse"],
                },
            ),
        ]

        def save_model(self, request, obj, form, change):
            """Auto-set created_by on new memberships."""
            if not change:  # New object
                obj.created_by = request.user
            super().save_model(request, obj, form, change)
