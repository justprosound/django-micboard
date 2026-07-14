"""Dashboard views for the micboard app."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.hardware.receiver_browse_dtos import ReceiverBrowseCriteria
from micboard.services.hardware.receiver_browse_service import ReceiverBrowseService
from micboard.services.monitoring.monitoring_access import MonitoringService


def _render_receiver_browse(
    request: HttpRequest,
    *,
    criteria: ReceiverBrowseCriteria,
) -> HttpResponse:
    """Render one bounded, tenant-scoped receiver page."""
    browse = ReceiverBrowseService.get_page(
        user=request.user,
        criteria=criteria,
        query_params=request.GET,
    )
    return render(request, "micboard/receiver_browse.html", {"browse": browse})


@login_required
@require_http_methods(["GET"])
def index(request: HttpRequest) -> HttpResponse:
    """Main dashboard view."""
    # Filter receivers based on user permissions
    user_receivers = WirelessChassis.objects.for_user(user=request.user)

    context = {
        "device_count": user_receivers.count(),
        "group_count": MonitoringService.get_user_monitoring_groups(request.user).count(),
    }
    return render(request, "micboard/index.html", context)


@require_http_methods(["GET"])
def about(request: HttpRequest) -> HttpResponse:
    """About page."""
    return render(request, "micboard/about.html")


@login_required
@require_http_methods(["GET"])
def device_type_view(request: HttpRequest, device_type: str) -> HttpResponse:
    """Display online chassis with an optional RF-role filter."""
    role = None if device_type == "all" else device_type
    role_labels = dict(WirelessChassis.DEVICE_ROLES)
    if role is not None and role not in role_labels:
        raise Http404("Unknown wireless chassis role")
    role_label = role_labels.get(role or "", role or "")
    title = "All online wireless chassis" if role is None else f"Online {role_label} chassis"
    return _render_receiver_browse(
        request,
        criteria=ReceiverBrowseCriteria(
            title=title,
            manufacturer_code=request.GET.get("manufacturer"),
            role=role,
        ),
    )


@login_required
@require_http_methods(["GET"])
def single_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    """View to display receivers in a specific building."""
    building_obj = get_object_or_404(
        MonitoringService.get_accessible_buildings(request.user),
        pk=building_id,
    )
    return _render_receiver_browse(
        request,
        criteria=ReceiverBrowseCriteria(
            title=f"Online wireless chassis in {building_obj.name}",
            manufacturer_code=request.GET.get("manufacturer"),
            building_id=building_obj.pk,
        ),
    )


@login_required
@require_http_methods(["GET"])
def performer_view(request: HttpRequest, performer_id: int) -> HttpResponse:
    """Display online chassis assigned to a named performer."""
    performer = get_object_or_404(
        Performer.objects.for_user(user=request.user),
        pk=performer_id,
    )
    return _render_receiver_browse(
        request,
        criteria=ReceiverBrowseCriteria(
            title=f"Online wireless chassis assigned to {performer.name}",
            manufacturer_code=request.GET.get("manufacturer"),
            performer_id=performer.pk,
        ),
    )


@login_required
@require_http_methods(["GET"])
def room_view(request: HttpRequest, room_id: int) -> HttpResponse:
    """View to display receivers in a specific room."""
    room_obj = get_object_or_404(
        MonitoringService.get_accessible_rooms(request.user).select_related("building"),
        pk=room_id,
    )

    return _render_receiver_browse(
        request,
        criteria=ReceiverBrowseCriteria(
            title=f"Online wireless chassis in {room_obj.building.name} / {room_obj.name}",
            manufacturer_code=request.GET.get("manufacturer"),
            building_id=room_obj.building_id,
            room_id=room_obj.pk,
        ),
    )


@login_required
@require_http_methods(["GET"])
def priority_view(request: HttpRequest, priority: str) -> HttpResponse:
    """View to display receivers with a specific assignment priority."""
    assignment_priority = None if priority == "all" else priority
    priority_labels = dict(PerformerAssignment.PRIORITY_CHOICES)
    if assignment_priority is not None and assignment_priority not in priority_labels:
        raise Http404("Unknown performer assignment priority")
    priority_label = priority_labels.get(priority, priority.replace("_", " ").title())
    title = (
        "All online wireless chassis"
        if assignment_priority is None
        else f"Online chassis with {priority_label} assignments"
    )
    return _render_receiver_browse(
        request,
        criteria=ReceiverBrowseCriteria(
            title=title,
            manufacturer_code=request.GET.get("manufacturer"),
            priority=assignment_priority,
        ),
    )


@login_required
@require_http_methods(["GET"])
def all_buildings_view(request: HttpRequest) -> HttpResponse:
    """View to display all buildings."""
    buildings = MonitoringService.get_accessible_buildings(request.user).order_by("name")
    context = {
        "buildings": buildings,
    }
    return render(request, "micboard/all_buildings_view.html", context)


@login_required
@require_http_methods(["GET"])
def all_rooms_view(request: HttpRequest) -> HttpResponse:
    """View to display all rooms."""
    rooms = (
        MonitoringService.get_accessible_rooms(request.user)
        .select_related("building")
        .order_by("building__name", "name")
    )
    context = {
        "rooms": rooms,
    }
    return render(request, "micboard/all_rooms_view.html", context)


@login_required
@require_http_methods(["GET"])
def rooms_in_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    """View to display all rooms within a specific building."""
    building_obj = get_object_or_404(
        MonitoringService.get_accessible_buildings(request.user),
        pk=building_id,
    )
    rooms = (
        MonitoringService.get_accessible_rooms(request.user)
        .filter(building=building_obj)
        .order_by("name")
    )
    context = {
        "building": building_obj,
        "rooms": rooms,
    }
    return render(request, "micboard/rooms_in_building_view.html", context)
