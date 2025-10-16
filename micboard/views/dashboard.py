"""
Dashboard views for the micboard app.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

# Updated imports
from micboard.models import Alert, Group, Location, Manufacturer, Receiver

User = get_user_model()


def index(request: HttpRequest):
    """Main dashboard view"""
    buildings = Location.objects.values_list("building", flat=True).distinct()
    rooms = Location.objects.values_list("room", flat=True).distinct()
    users = User.objects.all()
    manufacturers = Manufacturer.objects.filter(is_active=True)
    alert_types = Alert.ALERT_TYPES
    context = {
        "device_count": Receiver.objects.filter(is_active=True).count(),
        "group_count": Group.objects.count(),
        "buildings": buildings,
        "rooms": rooms,
        "users": users,
        "manufacturers": manufacturers,
        "alert_types": alert_types,
    }
    return render(request, "micboard/index.html", context)


def about(request: HttpRequest):
    """About page"""
    return render(request, "micboard/about.html")


def device_type_view(request: HttpRequest, device_type: str):
    """View to display receivers of a specific type"""
    manufacturer_code = request.GET.get("manufacturer")

    receivers_query = Receiver.objects.filter(device_type=device_type, is_active=True)

    # Filter by manufacturer if specified
    if manufacturer_code:
        receivers_query = receivers_query.filter(manufacturer__code=manufacturer_code)

    receivers = receivers_query  # Updated
    context = {
        "device_type": device_type,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/device_type_view.html", context)


def building_view(request: HttpRequest, building_name: str):
    """View to display receivers in a specific building"""
    manufacturer_code = request.GET.get("manufacturer")

    receivers_query = Receiver.objects.filter(
        channels__assignments__location__building=building_name, is_active=True
    ).distinct()

    # Filter by manufacturer if specified
    if manufacturer_code:
        receivers_query = receivers_query.filter(manufacturer__code=manufacturer_code)

    receivers = receivers_query  # Updated
    context = {
        "building_name": building_name,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/building_view.html", context)


def user_view(request: HttpRequest, username: str):
    """View to display receivers assigned to a specific user"""
    manufacturer_code = request.GET.get("manufacturer")

    receivers_query = Receiver.objects.filter(
        channels__assignments__user__username=username, is_active=True
    ).distinct()

    # Filter by manufacturer if specified
    if manufacturer_code:
        receivers_query = receivers_query.filter(manufacturer__code=manufacturer_code)

    receivers = receivers_query  # Updated
    context = {
        "username": username,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/user_view.html", context)


def room_view(request: HttpRequest, room_name: str):
    """View to display receivers in a specific room"""
    manufacturer_code = request.GET.get("manufacturer")

    receivers_query = Receiver.objects.filter(
        channels__assignments__location__room=room_name, is_active=True
    ).distinct()

    # Filter by manufacturer if specified
    if manufacturer_code:
        receivers_query = receivers_query.filter(manufacturer__code=manufacturer_code)

    receivers = receivers_query  # Updated
    context = {
        "room_name": room_name,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/room_view.html", context)


def priority_view(request: HttpRequest, priority: str):
    """View to display receivers with a specific assignment priority"""
    manufacturer_code = request.GET.get("manufacturer")

    receivers_query = Receiver.objects.filter(
        channels__assignments__priority=priority, is_active=True
    ).distinct()

    # Filter by manufacturer if specified
    if manufacturer_code:
        receivers_query = receivers_query.filter(manufacturer__code=manufacturer_code)

    receivers = receivers_query  # Updated
    context = {
        "priority": priority,
        "receivers": receivers,  # Updated
    }
    return render(request, "micboard/priority_view.html", context)


def alerts_view(request: HttpRequest) -> HttpResponse:
    """View to display and manage system alerts"""
    status_filter = request.GET.get("status", "pending")
    alert_type_filter = request.GET.get("type", "")
    page_number = request.GET.get("page", 1)

    # Base queryset
    alerts = Alert.objects.select_related("channel", "user").order_by("-created_at")

    # Apply filters
    if status_filter and status_filter != "all":
        alerts = alerts.filter(status=status_filter)
    if alert_type_filter:
        alerts = alerts.filter(alert_type=alert_type_filter)

    # Paginate results
    paginator = Paginator(alerts, 25)  # 25 alerts per page
    page_obj = paginator.get_page(page_number)

    # Alert statistics
    stats = {
        "total": Alert.objects.count(),
        "pending": Alert.objects.filter(status="pending").count(),
        "acknowledged": Alert.objects.filter(status="acknowledged").count(),
        "resolved": Alert.objects.filter(status="resolved").count(),
        "failed": Alert.objects.filter(status="failed").count(),
    }

    context = {
        "alerts": page_obj,
        "stats": stats,
        "status_filter": status_filter,
        "alert_type_filter": alert_type_filter,
        "alert_types": Alert.ALERT_TYPES,
        "alert_statuses": Alert.ALERT_STATUS,
    }
    return render(request, "micboard/alerts.html", context)


def alert_detail_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to display detailed information about a specific alert"""
    alert = get_object_or_404(Alert.objects.select_related("channel", "user"), id=alert_id)

    context = {
        "alert": alert,
    }
    return render(request, "micboard/alert_detail.html", context)


def acknowledge_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to acknowledge an alert"""
    if request.method != "POST":
        return redirect("alert_detail", alert_id=alert_id)

    alert = get_object_or_404(Alert, id=alert_id)
    alert.acknowledge(request.user if request.user.is_authenticated else None)
    messages.success(request, f"Alert '{alert}' has been acknowledged.")
    return redirect("alerts")


def resolve_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to resolve an alert"""
    if request.method != "POST":
        return redirect("alert_detail", alert_id=alert_id)

    alert = get_object_or_404(Alert, id=alert_id)
    alert.resolve()
    messages.success(request, f"Alert '{alert}' has been resolved.")
    return redirect("alerts")
