"""Admin configuration for display walls and kiosks."""

from __future__ import annotations

from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import DisplayWall, WallSection


class WallSectionInline(admin.TabularInline):
    """Inline admin for wall sections."""

    model = WallSection
    extra = 1
    filter_horizontal = ("chargers",)


@admin.register(DisplayWall)
class DisplayWallAdmin(MicboardModelAdmin):
    """Admin configuration for DisplayWall model."""

    list_display = (
        "name",
        "location",
        "kiosk_id",
        "orientation",
        "refresh_interval_seconds",
        "is_active",
        "last_heartbeat",
    )
    list_filter = ("location", "orientation", "is_active")
    search_fields = ("name", "kiosk_id")
    inlines = [WallSectionInline]
    readonly_fields = ("last_heartbeat",)
    list_select_related = ("location",)


@admin.register(WallSection)
class WallSectionAdmin(MicboardModelAdmin):
    """Admin configuration for WallSection model."""

    list_display = ("name", "wall", "layout", "is_active", "display_order")
    list_filter = ("wall__location", "wall", "layout", "is_active")
    search_fields = ("name", "wall__name")
    filter_horizontal = ("chargers",)
    list_select_related = ("wall", "wall__location")
