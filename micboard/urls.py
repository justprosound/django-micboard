"""
URL configuration for the Micboard Django app.

This module defines URL patterns for:
- Dashboard views (index, building, room, user, device type, priority, about)
- API endpoints (health, data, receivers, discover, refresh)
- Configuration and group management
"""

from __future__ import annotations

from django.urls import include, path

from micboard.views import dashboard
from micboard.views.api import (
    APIDocumentationView,
    ConfigHandler,
    GroupUpdateHandler,
    HealthCheckView,
    ReadinessCheckView,
    api_discover,
    api_health,
    api_receiver_detail,
    api_receivers_list,
    api_refresh,
    data_json,
)

urlpatterns = [
    # Dashboard views
    path("", dashboard.index, name="index"),
    path("building/<str:building>/", dashboard.building_view, name="building_view"),
    path("room/<str:building>/<str:room>/", dashboard.room_view, name="room_view"),
    path("user/<int:user_id>/", dashboard.user_view, name="user_view"),
    path("type/<str:device_type>/", dashboard.device_type_view, name="device_type_view"),
    path("priority/<str:priority>/", dashboard.priority_view, name="priority_view"),
    path("alerts/", dashboard.alerts_view, name="alerts"),
    path("alerts/<int:alert_id>/", dashboard.alert_detail_view, name="alert_detail"),
    path(
        "alerts/<int:alert_id>/acknowledge/",
        dashboard.acknowledge_alert_view,
        name="acknowledge_alert",
    ),
    path("alerts/<int:alert_id>/resolve/", dashboard.resolve_alert_view, name="resolve_alert"),
    path("about/", dashboard.about, name="about"),
    # API endpoints (current version - v1)
    path("api/health/", api_health, name="api_health"),
    path("api/health/detailed/", HealthCheckView.as_view(), name="api_health_detailed"),
    path("api/health/ready/", ReadinessCheckView.as_view(), name="api_health_ready"),
    path("api/docs/", APIDocumentationView.as_view(), name="api_docs"),
    path("api/data.json", data_json, name="data_json"),
    path("api/receivers/", api_receivers_list, name="api_receivers_list"),
    path("api/receivers/<int:receiver_id>/", api_receiver_detail, name="api_receiver_detail"),
    path("api/discover/", api_discover, name="api_discover"),
    path("api/refresh/", api_refresh, name="api_refresh"),
    # Class-based API views
    path("api/config/", ConfigHandler.as_view(), name="api_config"),
    path("api/groups/<int:group_id>/", GroupUpdateHandler.as_view(), name="api_group_update"),
    # Versioned API (explicit v1)
    path(
        "api/v1/",
        include(
            [
                path("health/", api_health, name="api_v1_health"),
                path("health/detailed/", HealthCheckView.as_view(), name="api_v1_health_detailed"),
                path("health/ready/", ReadinessCheckView.as_view(), name="api_v1_health_ready"),
                path("docs/", APIDocumentationView.as_view(), name="api_v1_docs"),
                path("data.json", data_json, name="api_v1_data_json"),
                path("receivers/", api_receivers_list, name="api_v1_receivers_list"),
                path(
                    "receivers/<int:receiver_id>/",
                    api_receiver_detail,
                    name="api_v1_receiver_detail",
                ),
                path("discover/", api_discover, name="api_v1_discover"),
                path("refresh/", api_refresh, name="api_v1_refresh"),
                path("config/", ConfigHandler.as_view(), name="api_v1_config"),
                path(
                    "groups/<int:group_id>/",
                    GroupUpdateHandler.as_view(),
                    name="api_v1_group_update",
                ),
            ]
        ),
    ),
]
