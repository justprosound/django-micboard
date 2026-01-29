import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static

logger = logging.getLogger(__name__)


def charger_display(request: HttpRequest) -> HttpResponse:
    """View to display the status of networked charging stations and microphones.

    Data is retrieved from database chargers.
    """
    from micboard.models import Charger

    chargers = Charger.objects.filter(is_active=True).order_by("order").prefetch_related("slots")

    charging_stations_data = []
    for charger in chargers:
        station_slots = []
        for slot in charger.slots.all().order_by("slot_number"):
            slot_data = {
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

    context = {
        "page_title": "Charger Display",
        "charging_stations": charging_stations_data,
        "error_message": None,
    }
    return render(request, "chargers/charger_display.html", context)
