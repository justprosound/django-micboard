from django.urls import path

from . import views

app_name = "micboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/data/", views.data_json, name="data_json"),
    path("api/health/", views.api_health, name="api_health"),
    path("api/receivers/", views.api_receivers_list, name="api_receivers_list"),
    path("api/receivers/<str:receiver_id>/", views.api_receiver_detail, name="api_receiver_detail"),
    path("api/config/", views.ConfigHandler.as_view(), name="config_update"),
    path("api/group/", views.GroupUpdateHandler.as_view(), name="group_update"),
    path("api/discover/", views.api_discover, name="api_discover"),
    path("api/refresh/", views.api_refresh, name="api_refresh"),
    path("about/", views.about, name="about"),
    path("device-type/<str:device_type>/", views.device_type_view, name="device_type_view"),
    path("building/<str:building_name>/", views.building_view, name="building_view"),
    path("user/<str:username>/", views.user_view, name="user_view"),
    path("room/<str:room_name>/", views.room_view, name="room_view"),
    path("priority/<str:priority>/", views.priority_view, name="priority_view"),
]
