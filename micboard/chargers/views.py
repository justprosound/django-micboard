import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def charger_display(request: HttpRequest) -> HttpResponse:
    """
    View to display the status of networked charging stations and microphones.
    Data is retrieved from database receivers that are chargers.
    """
    from micboard.models import Receiver

    charger_types = ["SBC250", "SBC850", "MXWNCS8", "MXWNCS4", "SBC220"]
    chargers = (
        Receiver.objects.filter(device_type__in=charger_types, is_active=True)
        .order_by("order")
        .prefetch_related("channels__transmitter")
    )

    charging_stations_data = []
    for charger in chargers:
        station_slots = []
        for channel in charger.channels.all().order_by("channel_number"):
            slot_data = {
                "slot_number": channel.channel_number,
                "image": channel.image.url if channel.image else None,
            }
            if hasattr(channel, "transmitter"):
                tx = channel.transmitter
                slot_data.update(
                    {
                        "mic_name": tx.name or f"Slot {tx.slot}",
                        "battery_level": tx.battery_percentage or 0,
                        "charging": getattr(tx, "charging_status", False),
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
                "status": "online" if charger.is_active else "offline",
                "slots": station_slots,
            }
        )

    context = {
        "page_title": "Charger Display",
        "charging_stations": charging_stations_data,
        "error_message": None,
    }
    return render(request, "chargers/charger_display.html", context)
