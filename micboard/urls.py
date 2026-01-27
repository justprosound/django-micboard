from django.urls import path

from micboard.chargers.views import charger_display
from micboard.views.alerts import alert_detail_view, alerts_view
from micboard.views.assignments import (
    AssignmentListView,
    create_assignment,
    delete_assignment,
    update_assignment,
)
from micboard.views.charger_dashboard import ChargerDashboardView
from micboard.views.dashboard import (
    about,
    all_buildings_view,
    device_type_view,
    index,
    priority_view,
    room_view,
    single_building_view,
)
from micboard.views.kiosk import (
    DisplayWallDetailView,
    DisplayWallListView,
    KioskAuthView,
    KioskDataView,
    KioskHealthView,
    WallSectionListView,
)

urlpatterns = [
    # UI Views
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("alerts/", alerts_view, name="alerts"),
    path("alerts/<int:alert_id>/", alert_detail_view, name="alert_detail"),
    path("chargers/", ChargerDashboardView.as_view(), name="charger_dashboard"),
    path("chargers/display/", charger_display, name="charger_display"),
    # Dashboard views
    path("buildings/", all_buildings_view, name="all_buildings_view"),
    path("building/<str:building>/", single_building_view, name="single_building_view"),
    path("room/<str:building>/<str:room>/", room_view, name="room_view"),
    path("device-type/<str:device_type>/", device_type_view, name="device_type_view"),
    path("priority/<str:priority>/", priority_view, name="priority_view"),
    # Assignment Management
    path("assignments/", AssignmentListView.as_view(), name="assignments"),
    path("assignments/create/", create_assignment, name="create_assignment"),
    path("assignments/<int:pk>/update/", update_assignment, name="update_assignment"),
    path("assignments/<int:pk>/delete/", delete_assignment, name="delete_assignment"),
    # Kiosk/Display Wall
    path("walls/", DisplayWallListView.as_view(), name="display_wall_list"),
    path("walls/<int:pk>/", DisplayWallDetailView.as_view(), name="display_wall_detail"),
    path("walls/<int:wall_id>/sections/", WallSectionListView.as_view(), name="wall_section_list"),
    path("walls/<int:wall_id>/data/", KioskDataView.as_view(), name="kiosk_data"),
    path("walls/<int:wall_id>/health/", KioskHealthView.as_view(), name="kiosk_health"),
    path("kiosk/<str:kiosk_id>/", KioskAuthView.as_view(), name="kiosk_display"),
]
