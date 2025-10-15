"""
Views for the micboard app.

This module imports views from submodules for better organization.
"""
from .views.api import (
    ConfigHandler,
    GroupUpdateHandler,
    api_discover,
    api_health,
    api_receiver_detail,
    api_receivers_list,
    api_refresh,
    data_json,
)
from .views.dashboard import (
    about,
    building_view,
    device_type_view,
    index,
    priority_view,
    room_view,
    user_view,
)

__all__ = [
    "about",
    "api_discover",
    "api_health",
    "api_receiver_detail",
    "api_receivers_list",
    "api_refresh",
    "ConfigHandler",
    "data_json",
    "GroupUpdateHandler",
    "index",
    "device_type_view",
    "building_view",
    "user_view",
    "room_view",
    "priority_view",
]
