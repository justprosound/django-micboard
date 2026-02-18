"""HTMX partial fragment endpoints."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.performer_assignment import PerformerAssignment


@login_required
def channel_card_partial(request: HttpRequest, channel_id: int) -> HttpResponse:
    """HTMX partial: single channel status card."""
    from micboard.models import RFChannel

    channel = get_object_or_404(RFChannel, id=channel_id)
    return render(request, "micboard/partials/channel_card.html", {"channel": channel})


@login_required
def charger_slot_partial(request: HttpRequest, slot_id: int) -> HttpResponse:
    """HTMX partial: charger slot status."""
    from micboard.models import ChargerSlot

    slot = get_object_or_404(ChargerSlot, id=slot_id)
    return render(request, "micboard/partials/charger_slot.html", {"slot": slot})


@login_required
def wall_section_partial(request: HttpRequest, section_id: int) -> HttpResponse:
    """HTMX partial: display wall section with chargers."""
    from micboard.models import WallSection
    from micboard.services.kiosk import KioskService

    section = get_object_or_404(WallSection, id=section_id)
    data = KioskService.get_section_data(section.id)
    return render(
        request,
        "micboard/partials/wall_section.html",
        {"section": section, "data": data},
    )


@login_required
def alert_row_partial(request: HttpRequest, alert_id: int) -> HttpResponse:
    """HTMX partial: alert table row."""
    alert = get_object_or_404(Alert, id=alert_id)
    return render(request, "micboard/partials/alert_row.html", {"alert": alert})


@login_required
def assignment_row_partial(request: HttpRequest, assignment_id: int) -> HttpResponse:
    """HTMX partial: performer assignment row."""
    assignment = get_object_or_404(PerformerAssignment, id=assignment_id)
    return render(request, "micboard/partials/assignment_row.html", {"assignment": assignment})


@login_required
def charger_grid_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial: full charger dashboard grid."""
    from micboard.services.kiosk import KioskService

    data = KioskService.get_charger_dashboard_data()
    return render(request, "micboard/partials/charger_grid.html", data)


@login_required
def device_tiles_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial: dashboard device status tiles."""
    user_chassis = WirelessChassis.objects.for_user(user=request.user).filter(is_online=True)
    return render(request, "micboard/partials/device_tiles.html", {"chassis": user_chassis})
