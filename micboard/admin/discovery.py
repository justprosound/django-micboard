"""Admin configuration for discovery models (DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob).

This module provides Django admin interfaces for managing device discovery configurations and jobs.
"""

from __future__ import annotations

from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.discovery import DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob


@admin.register(DiscoveryCIDR)
class DiscoveryCIDRAdmin(MicboardModelAdmin):
    """Admin configuration for DiscoveryCIDR model."""

    list_display = ("manufacturer", "cidr", "created_at")
    list_filter = ("manufacturer",)
    search_fields = ("cidr",)
    list_select_related = ("manufacturer",)


@admin.register(DiscoveryFQDN)
class DiscoveryFQDNAdmin(MicboardModelAdmin):
    """Admin configuration for DiscoveryFQDN model."""

    list_display = ("manufacturer", "fqdn", "created_at")
    list_filter = ("manufacturer",)
    search_fields = ("fqdn",)
    list_select_related = ("manufacturer",)


@admin.register(DiscoveryJob)
class DiscoveryJobAdmin(MicboardModelAdmin):
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
    list_select_related = ("manufacturer",)
    readonly_fields = ("created_at", "started_at", "finished_at")
