"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from micboard.models import Alert

# Alert business logic has been moved to the service layer
# (see `micboard.services.monitoring.alerts.AlertManager`).
#
# Views in this module are intentionally thin and only handle
# request/response concerns (rendering, pagination, flash messages).
# Business logic and alert creation/notification must be invoked
# via the monitoring services; do not reintroduce it here.


@login_required
@require_http_methods(["GET"])
def alerts_view(request: HttpRequest) -> HttpResponse:
    """View to display and manage system alerts."""
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


@login_required
@require_http_methods(["GET"])
def alert_detail_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to display detailed information about a specific alert."""
    alert = get_object_or_404(Alert.objects.select_related("channel", "user"), id=alert_id)

    context = {
        "alert": alert,
    }
    return render(request, "micboard/alert_detail.html", context)


@login_required
@require_http_methods(["POST"])
def acknowledge_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to acknowledge an alert (delegates to service)."""
    from micboard.services.monitoring.alerts import acknowledge_alert

    acknowledge_alert(alert_id=alert_id, user=request.user)
    messages.success(request, "Alert has been acknowledged.")
    return redirect(request.headers.get("referer") or "alerts")


@login_required
@require_http_methods(["POST"])
def resolve_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to resolve an alert (delegates to service)."""
    from micboard.services.monitoring.alerts import resolve_alert

    resolve_alert(alert_id=alert_id)
    messages.success(request, "Alert has been resolved.")
    return redirect(request.headers.get("referer") or "alerts")
