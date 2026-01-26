"""Dashboard views for the micboard app."""

from typing import Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, render

# Updated imports
from micboard.models import Alert, Building, Group, Manufacturer, Room, WirelessChassis

User = get_user_model()


def get_filtered_receivers(request: HttpRequest, manufacturer_code: Optional[str], **filters):
    """Helper function to get filtered receivers for dashboard views."""
    qs = WirelessChassis.objects.for_user(request.user).filter(**filters)

    if manufacturer_code:
        # Use the manager method if available or filter directly
        if hasattr(qs, "by_manufacturer"):
            qs = qs.by_manufacturer(manufacturer=manufacturer_code)
        else:
            qs = qs.filter(manufacturer__code=manufacturer_code)

    return qs.distinct()


def index(request: HttpRequest):
    """Main dashboard view."""
    buildings = Building.objects.all()
    rooms = Room.objects.all()
    users = User.objects.all()
    manufacturers = Manufacturer.objects.filter(status__in=["online", "degraded", "provisioning"])
    alert_types = Alert.ALERT_TYPES

    # Filter receivers based on user permissions
    user_receivers = WirelessChassis.objects.for_user(request.user)

    context = {
        "device_count": user_receivers.count(),
        "group_count": Group.objects.count(),
        "buildings": buildings,
        "rooms": rooms,
        "users": users,
        "manufacturers": manufacturers,
        "alert_types": alert_types,
    }
    return render(request, "micboard/index.html", context)


def about(request: HttpRequest):
    """About page."""
    return render(request, "micboard/about.html")


def device_type_view(request: HttpRequest, device_type: str):
    """View to display receivers of a specific type."""
    manufacturer_code = request.GET.get("manufacturer")

    # Map device_type to role if necessary, or filter by role
    # Assuming device_type param maps to WirelessChassis.role
    receivers = get_filtered_receivers(request, manufacturer_code, role=device_type, is_online=True)

    context = {
        "device_type": device_type,
        "receivers": receivers,
    }
    return render(request, "micboard/device_type_view.html", context)


def single_building_view(request: HttpRequest, building: str):
    """View to display receivers in a specific building."""
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


def user_view(request: HttpRequest, username: str):
    """View to display receivers assigned to a specific user."""
    manufacturer_code = request.GET.get("manufacturer")

    # Path: rf_channels -> assignments -> user
    receivers = get_filtered_receivers(
        request,
        manufacturer_code,
        rf_channels__assignments__user__username=username,
        is_online=True,
    )

    context = {
        "username": username,
        "receivers": receivers,
    }
    return render(request, "micboard/user_view.html", context)


def room_view(request: HttpRequest, building: str, room: str):
    """View to display receivers in a specific room."""
    manufacturer_code = request.GET.get("manufacturer")

    # Get the Building and Room objects
    building_obj = get_object_or_404(Building, name=building)
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


def priority_view(request: HttpRequest, priority: str):
    """View to display receivers with a specific assignment priority."""
    manufacturer_code = request.GET.get("manufacturer")

    receivers = get_filtered_receivers(
        request, manufacturer_code, rf_channels__assignments__priority=priority, is_online=True
    )

    context = {
        "priority": priority,
        "receivers": receivers,
    }
    return render(request, "micboard/priority_view.html", context)


def all_buildings_view(request: HttpRequest):
    """View to display all buildings."""
    buildings = Building.objects.all()
    context = {
        "buildings": buildings,
    }
    return render(request, "micboard/all_buildings_view.html", context)


def all_rooms_view(request: HttpRequest):
    """View to display all rooms."""
    rooms = Room.objects.all()
    context = {
        "rooms": rooms,
    }
    return render(request, "micboard/all_rooms_view.html", context)


def rooms_in_building_view(request: HttpRequest, building: str):
    """View to display all rooms within a specific building."""
    building_obj = get_object_or_404(Building, name=building)
    rooms = Room.objects.filter(building=building_obj)
    context = {
        "building_name": building,
        "rooms": rooms,
    }
    return render(request, "micboard/rooms_in_building_view.html", context)
