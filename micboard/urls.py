"""
URL configuration for the Micboard Django app.

This module defines URL patterns for:
- Dashboard views (index, building, room, user, device type, priority, about)
- API endpoints (health, data, receivers, discover, refresh)
- Configuration and group management
"""
from __future__ import annotations

from django.urls import path

from micboard.views import dashboard
from micboard.views.api import (
    ConfigHandler,
    GroupUpdateHandler,
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
    path("about/", dashboard.about, name="about"),
    # API endpoints
    path("api/health/", api_health, name="api_health"),
    path("api/data.json", data_json, name="data_json"),
    path("api/receivers/", api_receivers_list, name="api_receivers_list"),
    path("api/receivers/<int:receiver_id>/", api_receiver_detail, name="api_receiver_detail"),
    path("api/discover/", api_discover, name="api_discover"),
    path("api/refresh/", api_refresh, name="api_refresh"),
    # Class-based API views
    path("api/config/", ConfigHandler.as_view(), name="api_config"),
    path("api/groups/<int:group_id>/", GroupUpdateHandler.as_view(), name="api_group_update"),
]
