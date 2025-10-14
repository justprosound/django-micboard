"""
Dashboard views for the micboard app.
"""
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.shortcuts import render

# Updated imports
from micboard.models import Group, Location, Receiver

User = get_user_model()


def index(request: HttpRequest):
    """Main dashboard view"""
    buildings = Location.objects.values_list("building", flat=True).distinct()
    rooms = Location.objects.values_list("room", flat=True).distinct()
    users = User.objects.all()
    context = {
        "device_count": Receiver.objects.filter(is_active=True).count(),  # Updated
        "group_count": Group.objects.count(),
        "buildings": buildings,
        "rooms": rooms,
        "users": users,
    }
    return render(request, "micboard/index.html", context)


def about(request: HttpRequest):
    """About page"""
    return render(request, "micboard/about.html")


def device_type_view(request: HttpRequest, device_type: str):
    """View to display receivers of a specific type"""
    receivers = Receiver.objects.filter(device_type=device_type, is_active=True)  # Updated
    context = {
        "device_type": device_type,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/device_type_view.html", context)


def building_view(request: HttpRequest, building_name: str):
    """View to display receivers in a specific building"""
    receivers = Receiver.objects.filter(
        channels__assignments__location__building=building_name, is_active=True
    ).distinct()  # Updated
    context = {
        "building_name": building_name,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/building_view.html", context)


def user_view(request: HttpRequest, username: str):
    """View to display receivers assigned to a specific user"""
    receivers = Receiver.objects.filter(
        channels__assignments__user__username=username, is_active=True
    ).distinct()  # Updated
    context = {
        "username": username,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/user_view.html", context)


def room_view(request: HttpRequest, room_name: str):
    """View to display receivers in a specific room"""
    receivers = Receiver.objects.filter(
        channels__assignments__location__room=room_name, is_active=True
    ).distinct()  # Updated
    context = {
        "room_name": room_name,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/room_view.html", context)


def priority_view(request: HttpRequest, priority: str):
    """View to display receivers with a specific assignment priority"""
    receivers = Receiver.objects.filter(
        channels__assignments__priority=priority, is_active=True
    ).distinct()  # Updated
    context = {
        "priority": priority,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/priority_view.html", context)
