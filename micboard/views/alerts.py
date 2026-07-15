"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_browse_dtos import AlertBrowseCriteria
from micboard.services.monitoring.alert_browse_service import AlertBrowseService
from micboard.services.monitoring.alerts import (
    acknowledge_alert,
    get_alerts_for_user,
    resolve_alert,
)

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
    criteria = AlertBrowseCriteria(
        status=request.GET.get("status", "pending"),
        alert_type=request.GET.get("type", ""),
        page=request.GET.get("page", 1),
    )
    browse = AlertBrowseService.get_page(user=request.user, criteria=criteria)

    context = {
        "browse": browse,
        "stats": AlertBrowseService.get_stats(user=request.user),
        "status_filter": criteria.status,
        "alert_type_filter": criteria.alert_type,
        "alert_types": Alert.ALERT_TYPES,
        "alert_statuses": Alert.ALERT_STATUS,
    }
    return render(request, "micboard/alerts.html", context)


@login_required
@require_http_methods(["GET"])
def alert_rows_view(request: HttpRequest) -> HttpResponse:
    """Return only bounded alert rows for live refreshes."""
    browse = AlertBrowseService.get_rows(
        user=request.user,
        criteria=AlertBrowseCriteria(
            status=request.GET.get("status", "pending"),
            alert_type=request.GET.get("type", ""),
            page=request.GET.get("page", 1),
        ),
    )
    return render(request, "micboard/partials/alert_rows.html", {"browse": browse})


@login_required
@require_http_methods(["GET"])
def alert_detail_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to display detailed information about a specific alert."""
    alert = get_object_or_404(
        get_alerts_for_user(request.user).select_related(
            "assignment__performer",
            "assignment__wireless_unit__base_chassis__location",
            "channel__chassis",
            "user",
        ),
        id=alert_id,
    )

    context = {
        "alert": alert,
    }
    return render(request, "micboard/alert_detail.html", context)


@login_required
@require_http_methods(["POST"])
def acknowledge_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to acknowledge an alert (delegates to service)."""
    try:
        acknowledge_alert(alert_id=alert_id, user=request.user)
    except Alert.DoesNotExist:
        raise Http404("Alert not found") from None
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("micboard:alerts")
    messages.success(request, "Alert has been acknowledged.")
    return redirect("micboard:alerts")


@login_required
@require_http_methods(["POST"])
def resolve_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to resolve an alert (delegates to service)."""
    try:
        resolve_alert(alert_id=alert_id, user=request.user)
    except Alert.DoesNotExist:
        raise Http404("Alert not found") from None
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("micboard:alerts")
    messages.success(request, "Alert has been resolved.")
    return redirect("micboard:alerts")
