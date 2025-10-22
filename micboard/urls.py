"""
URL configuration for the Micboard Django app.

This module defines URL patterns for:
- Dashboard views (index, building, room, user, device type, priority, about)
- API endpoints (health, data, receivers, discover, refresh)
- Configuration and group management
"""

from __future__ import annotations

from django.urls import include, path

from micboard.chargers import views as charger_views
from micboard.views import alerts
from micboard.views.dashboard import dashboard
from micboard.views.user_views import RecordUserView

urlpatterns = [
    # Dashboard views
    path("", dashboard.index, name="index"),
    path("building/<str:building>/", dashboard.building_view, name="building_view"),
    path("room/<str:building>/<str:room>/", dashboard.room_view, name="room_view"),
    path("user/<str:username>/", dashboard.user_view, name="user_view"),
    path("type/<str:device_type>/", dashboard.device_type_view, name="device_type_view"),
    path("priority/<str:priority>/", dashboard.priority_view, name="priority_view"),
    path("alerts/", alerts.alerts_view, name="alerts"),
    path("alerts/<int:alert_id>/", alerts.alert_detail_view, name="alert_detail"),
    path(
        "alerts/<int:alert_id>/acknowledge/",
        alerts.acknowledge_alert_view,
        name="acknowledge_alert",
    ),
    path("alerts/<int:alert_id>/resolve/", alerts.resolve_alert_view, name="resolve_alert"),
    path("about/", dashboard.about, name="about"),
    path("chargers/", charger_views.charger_display, name="charger_display"),
    path("record-view/", RecordUserView.as_view(), name="record-view"),
    # API endpoints (current version - v1)
    path("api/v1/", include("micboard.api.v1.urls")),
    # Note: legacy compatibility routes removed. Use API v1 endpoints under /api/v1/.
]
