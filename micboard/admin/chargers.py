from django.contrib import admin

from micboard.models import Charger, ChargerSlot


@admin.register(ChargerSlot)
class ChargerSlotAdmin(admin.ModelAdmin):
    list_display = ("charger", "slot_number", "is_occupied", "transmitter", "charging_status")
    list_filter = ("charger", "is_occupied", "charging_status")
    search_fields = ("charger__name", "transmitter__name")


@admin.register(Charger)
class ChargerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "manufacturer",
        "device_type",
        "ip",
        "is_active",
        "last_seen",
        "location",
    )
    list_filter = ("manufacturer", "device_type", "is_active", "location")
    search_fields = ("name", "api_device_id", "ip")
    readonly_fields = ("last_seen",)
    ordering = ("order", "manufacturer__name", "name")
