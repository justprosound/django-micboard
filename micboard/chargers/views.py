from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from micboard.services.chargers.charger_display_service import get_charging_stations_data


@login_required
def charger_display(request: HttpRequest) -> HttpResponse:
    """View to display the status of networked charging stations and microphones (delegates to service)."""
    context = {
        "page_title": "Charger Display",
        "charging_stations": get_charging_stations_data(user=request.user),
        "error_message": None,
    }
    return render(request, "chargers/charger_display.html", context)
