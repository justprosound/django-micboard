"""Dashboard views for the micboard app."""

from typing import Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from micboard.filters import HAS_DJANGO_FILTERS, WirelessChassisFilter

# Updated imports
from micboard.models import Building, MonitoringGroup, Room, WirelessChassis

User = get_user_model()


def get_filtered_receivers(request: HttpRequest, manufacturer_code: Optional[str], **filters):
    """Helper function to get filtered receivers for dashboard views."""
    qs = WirelessChassis.objects.for_user(user=request.user).filter(**filters)

    if HAS_DJANGO_FILTERS:
        # Use django-filter if available
        f = WirelessChassisFilter(request.GET, queryset=qs)
        qs = f.qs

    if manufacturer_code:
        # Use the manager method if available or filter directly
        if hasattr(qs, "by_manufacturer"):
            qs = qs.by_manufacturer(manufacturer=manufacturer_code)
        else:
            qs = qs.filter(manufacturer__code=manufacturer_code)

    return qs.distinct()


@require_http_methods(["GET"])
def index(request: HttpRequest):
    """Main dashboard view."""
    # Filter receivers based on user permissions
    user_receivers = WirelessChassis.objects.for_user(user=request.user)

    context = {
        "device_count": user_receivers.count(),
        "group_count": MonitoringGroup.objects.count(),
    }
    return render(request, "micboard/index.html", context)


@require_http_methods(["GET"])
def about(request: HttpRequest):
    """About page."""
    return render(request, "micboard/about.html")


@require_http_methods(["GET"])
def device_type_view(request: HttpRequest, device_type: str):
    """View to display receivers of a specific type."""
    manufacturer_code = request.GET.get("manufacturer")

    # Map device_type to role if necessary, or filter by role
    # Assuming device_type param maps to WirelessChassis.role
    # Handle 'all' case - show all devices regardless of type
    if device_type == "all":
        receivers = get_filtered_receivers(request, manufacturer_code, is_online=True)
    else:
        receivers = get_filtered_receivers(
            request, manufacturer_code, role=device_type, is_online=True
        )

    context = {
        "device_type": device_type,
        "receivers": receivers,
    }
    return render(request, "micboard/device_type_view.html", context)


@require_http_methods(["GET"])
def single_building_view(request: HttpRequest, building: str):
    """View to display receivers in a specific building."""
    # Handle special 'all' case
    if building == "all":
        return all_buildings_view(request)

    manufacturer_code = request.GET.get("manufacturer")

    # Get the Building object
    building_obj = get_object_or_404(Building, name=building)

    # status="online" replaces is_active=True/is_online=True usually,
    # but lets stick to is_online field
    receivers = get_filtered_receivers(
        request, manufacturer_code, location__building=building_obj, is_online=True
    )

    context = {
        "building_name": building,
        "receivers": receivers,
    }
    return render(request, "micboard/building_view.html", context)


@require_http_methods(["GET"])
def user_view(request: HttpRequest, username: str):
    """View to display receivers assigned to a specific performer."""
    manufacturer_code = request.GET.get("manufacturer")

    # Filter by performer (field_units -> performer_assignments -> performer -> name)
    receivers = get_filtered_receivers(
        request,
        manufacturer_code,
        field_units__performer_assignments__performer__name=username,
        is_online=True,
    )

    context = {
        "username": username,
        "receivers": receivers,
    }
    return render(request, "micboard/user_view.html", context)


@require_http_methods(["GET"])
def room_view(request: HttpRequest, building: str, room: str):
    """View to display receivers in a specific room."""
    # Handle special 'all' cases
    if building == "all" and room == "all":
        return all_rooms_view(request)
    elif building == "all":
        return all_buildings_view(request)

    manufacturer_code = request.GET.get("manufacturer")

    # Get the Building and Room objects
    building_obj = get_object_or_404(Building, name=building)

    # Handle 'all' rooms in a specific building
    if room == "all":
        return rooms_in_building_view(request, building)

    room_obj = get_object_or_404(Room, building=building_obj, name=room)

    receivers = get_filtered_receivers(
        request,
        manufacturer_code,
        location__building=building_obj,
        location__room=room_obj,
        is_online=True,
    )

    context = {
        "building": building,
        "room_name": room,
        "receivers": receivers,
    }
    return render(request, "micboard/room_view.html", context)


@require_http_methods(["GET"])
def priority_view(request: HttpRequest, priority: str):
    """View to display receivers with a specific assignment priority."""
    manufacturer_code = request.GET.get("manufacturer")

    # Handle 'all' case - show all priorities
    if priority == "all":
        receivers = get_filtered_receivers(request, manufacturer_code, is_online=True)
    else:
        # Correct path: chassis -> field_units -> performer_assignments -> priority
        receivers = get_filtered_receivers(
            request,
            manufacturer_code,
            field_units__performer_assignments__priority=priority,
            is_online=True,
        )

    context = {
        "priority": priority,
        "receivers": receivers,
    }
    return render(request, "micboard/priority_view.html", context)


@require_http_methods(["GET"])
def all_buildings_view(request: HttpRequest):
    """View to display all buildings."""
    buildings = Building.objects.all().order_by("name")
    context = {
        "buildings": buildings,
    }
    return render(request, "micboard/all_buildings_view.html", context)


@require_http_methods(["GET"])
def all_rooms_view(request: HttpRequest):
    """View to display all rooms."""
    rooms = Room.objects.select_related("building").order_by("building__name", "name")
    context = {
        "rooms": rooms,
    }
    return render(request, "micboard/all_rooms_view.html", context)


@require_http_methods(["GET"])
def rooms_in_building_view(request: HttpRequest, building: str):
    """View to display all rooms within a specific building."""
    building_obj = get_object_or_404(Building, name=building)
    rooms = Room.objects.filter(building=building_obj).order_by("name")
    context = {
        "building_name": building,
        "rooms": rooms,
    }
    return render(request, "micboard/rooms_in_building_view.html", context)
