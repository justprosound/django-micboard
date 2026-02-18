from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from micboard.services.chargers.charger_display_service import get_charging_stations_data


def charger_display(request: HttpRequest) -> HttpResponse:
    """View to display the status of networked charging stations and microphones (delegates to service)."""
    context = {
        "page_title": "Charger Display",
        "charging_stations": get_charging_stations_data(),
        "error_message": None,
    }
    return render(request, "chargers/charger_display.html", context)
