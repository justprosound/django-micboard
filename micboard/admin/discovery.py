"""
Admin configuration for discovery models (DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob).

This module provides Django admin interfaces for managing device discovery configurations and jobs.
"""

from __future__ import annotations

from django.contrib import admin

from micboard.models.discovery import DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob


@admin.register(DiscoveryCIDR)
class DiscoveryCIDRAdmin(admin.ModelAdmin):
    """Admin configuration for DiscoveryCIDR model."""

    list_display = ("manufacturer", "cidr", "created_at")
    list_filter = ("manufacturer",)
    search_fields = ("cidr",)


@admin.register(DiscoveryFQDN)
class DiscoveryFQDNAdmin(admin.ModelAdmin):
    """Admin configuration for DiscoveryFQDN model."""

    list_display = ("manufacturer", "fqdn", "created_at")
    list_filter = ("manufacturer",)
    search_fields = ("fqdn",)


@admin.register(DiscoveryJob)
class DiscoveryJobAdmin(admin.ModelAdmin):
    """Admin configuration for DiscoveryJob model."""

    list_display = (
        "manufacturer",
        "action",
        "status",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("manufacturer", "status", "action")
    readonly_fields = ("created_at", "started_at", "finished_at")
