"""HTMX partial fragment endpoints."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.monitoring.alerts import get_alerts_for_user


@login_required
def channel_card_partial(request: HttpRequest, channel_id: int) -> HttpResponse:
    """HTMX partial: single channel status card."""
    from micboard.services.monitoring.monitoring_access import MonitoringService

    channel = get_object_or_404(
        MonitoringService.get_accessible_channels(request.user),
        id=channel_id,
    )
    return render(request, "micboard/partials/channel_card.html", {"channel": channel})


@login_required
def charger_slot_partial(request: HttpRequest, slot_id: int) -> HttpResponse:
    """HTMX partial: charger slot status."""
    from micboard.services.monitoring.monitoring_access import MonitoringService

    slot = get_object_or_404(
        MonitoringService.get_accessible_charger_slots(request.user), id=slot_id
    )
    return render(request, "micboard/partials/charger_slot.html", {"slot": slot})


@login_required
def wall_section_partial(request: HttpRequest, section_id: int) -> HttpResponse:
    """HTMX partial: display wall section with chargers."""
    from micboard.services.kiosk.services import KioskService

    snapshot = KioskService.get_section_snapshot(section_id, user=request.user)
    if snapshot is None:
        raise Http404("Wall section not found")
    return render(
        request,
        "micboard/partials/wall_section.html",
        {"snapshot": snapshot},
    )


@login_required
def alert_row_partial(request: HttpRequest, alert_id: int) -> HttpResponse:
    """HTMX partial: alert table row."""
    alert = get_object_or_404(
        get_alerts_for_user(request.user).select_related(
            "assignment__wireless_unit",
            "channel__chassis",
        ),
        id=alert_id,
    )
    return render(request, "micboard/partials/alert_row.html", {"alert": alert})


@login_required
def assignment_row_partial(request: HttpRequest, assignment_id: int) -> HttpResponse:
    """HTMX partial: performer assignment row."""
    assignment = get_object_or_404(
        PerformerAssignment.objects.for_user(user=request.user),
        id=assignment_id,
    )
    return render(request, "micboard/partials/assignment_row.html", {"assignment": assignment})


@login_required
def charger_grid_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial: full charger dashboard grid."""
    from micboard.services.chargers.dashboard_service import ChargerDashboardService

    snapshot = ChargerDashboardService.get_snapshot(user=request.user)
    return render(
        request,
        "micboard/partials/charger_grid.html",
        {"snapshot": snapshot},
    )


@login_required
def device_tiles_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial: dashboard device status tiles."""
    user_chassis = WirelessChassis.objects.for_user(user=request.user).filter(is_online=True)
    return render(request, "micboard/partials/device_tiles.html", {"chassis": user_chassis})
