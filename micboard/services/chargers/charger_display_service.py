"""Service for assembling charger display data."""

from typing import Any

from django.templatetags.static import static

from micboard.models.hardware.charger import Charger


def get_charging_stations_data(*, user) -> list[dict[str, Any]]:
    """Return charging-station data limited to the user's location scope."""
    chargers = (
        Charger.objects.for_user(user=user)
        .filter(is_active=True)
        .order_by("order")
        .prefetch_related("slots")
    )
    charging_stations_data: list[dict[str, Any]] = []
    for charger in chargers:
        station_slots: list[dict[str, Any]] = []
        for slot in charger.slots.all():
            slot_data: dict[str, Any] = {
                "slot_number": slot.slot_number,
                "image": None,
            }
            if slot.occupied:
                image_path = "micboard/images/field_unit_default.svg"
                if slot.device_model and slot.device_model.upper() == "ULXD1":
                    image_path = "micboard/images/ulxd1_wl185.svg"
                slot_data.update(
                    {
                        "mic_name": slot.device_model or f"Slot {slot.slot_number}",
                        "battery_level": slot.battery_percent or 0,
                        "charging": slot.device_status == "charging",
                        "image": static(image_path),
                    }
                )
            else:
                slot_data.update(
                    {
                        "mic_name": "Empty",
                        "battery_level": 0,
                        "charging": False,
                    }
                )
            station_slots.append(slot_data)
        charging_stations_data.append(
            {
                "id": charger.serial_number,
                "name": charger.name or f"Charger {charger.serial_number}",
                "status": "online" if charger.status == "online" else "offline",
                "slots": station_slots,
            }
        )
    return charging_stations_data
