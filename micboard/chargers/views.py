import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def charger_display(request: HttpRequest) -> HttpResponse:
    """View to display the status of networked charging stations and microphones.
    Data is retrieved from database chargers.
    """
    from micboard.models import Charger

    chargers = (
        Charger.objects.filter(is_active=True)
        .order_by("order")
        .prefetch_related("slots__transmitter")
    )

    charging_stations_data = []
    for charger in chargers:
        station_slots = []
        for slot in charger.slots.all().order_by("slot_number"):
            slot_data = {
                "slot_number": slot.slot_number,
                "image": None,  # TODO: add image field if needed
            }
            if slot.transmitter:
                tx = slot.transmitter
                slot_data.update(
                    {
                        "mic_name": tx.name or f"Slot {tx.slot}",
                        "battery_level": tx.battery_percentage or 0,
                        "charging": slot.charging_status,
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
                "id": charger.api_device_id,
                "name": charger.name or f"Charger {charger.api_device_id}",
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
