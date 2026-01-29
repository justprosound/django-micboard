from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin, MicboardSortableAdmin
from micboard.models import Charger, ChargerSlot


@admin.register(ChargerSlot)
class ChargerSlotAdmin(MicboardModelAdmin):
    list_display = (
        "charger",
        "slot_number",
        "is_occupied",
        "device_info",
        "battery_percent",
        "device_status",
    )
    list_filter = ("charger", "occupied", "device_status")
    search_fields = ("charger__name", "device_serial", "device_model")
    list_select_related = ("charger",)

    @admin.display(description="Device Info")
    def device_info(self, obj):
        if obj.device_model and obj.device_serial:
            return f"{obj.device_model} ({obj.device_serial})"
        return obj.device_serial or "-"

    @admin.display(boolean=True, description="Occupied")
    def is_occupied(self, obj):
        return obj.occupied


@admin.register(Charger)
class ChargerAdmin(MicboardSortableAdmin):
    list_display = (
        "name",
        "manufacturer",
        "device_type",
        "ip",
        "status",
        "last_seen",
        "location",
    )
    list_filter = ("manufacturer", "device_type", "status", "location")
    search_fields = ("name", "serial_number", "ip")
    list_select_related = ("manufacturer", "location")
    readonly_fields = ("last_seen",)
    ordering = ("order", "manufacturer__name", "name")
