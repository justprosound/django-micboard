from django.urls import path

from micboard.views.alerts import (
    acknowledge_alert_view,
    alert_detail_view,
    alert_rows_view,
    alerts_view,
    resolve_alert_view,
)
from micboard.views.assignments import (
    AssignmentListView,
    AssignmentRowsView,
    create_assignment,
    delete_assignment,
    update_assignment,
)
from micboard.views.charger_dashboard import ChargerDashboardView, ChargerGridView
from micboard.views.dashboard import (
    about,
    all_buildings_view,
    all_rooms_view,
    device_type_view,
    index,
    performer_view,
    priority_view,
    room_view,
    rooms_in_building_view,
    single_building_view,
)
from micboard.views.kiosk import (
    DisplayWallDetailView,
    DisplayWallListView,
    KioskAuthView,
    KioskContentView,
    KioskDataView,
    KioskHealthView,
    WallSectionListView,
)
from micboard.views.partials import (
    alert_row_partial,
    assignment_row_partial,
    channel_card_partial,
    charger_grid_partial,
    charger_slot_partial,
    device_tiles_partial,
    wall_section_partial,
)
from micboard.views.settings import (
    BulkSettingConfigView,
    ManufacturerSettingsView,
    settings_diff_view,
    settings_overview,
)

app_name = "micboard"

urlpatterns = [
    # UI Views
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("alerts/", alerts_view, name="alerts"),
    path("alerts/rows/", alert_rows_view, name="alert_rows"),
    path("alerts/<int:alert_id>/", alert_detail_view, name="alert_detail"),
    path(
        "alerts/<int:alert_id>/acknowledge/",
        acknowledge_alert_view,
        name="acknowledge_alert",
    ),
    path("alerts/<int:alert_id>/resolve/", resolve_alert_view, name="resolve_alert"),
    path("chargers/", ChargerDashboardView.as_view(), name="charger_dashboard"),
    path("chargers/grid/", ChargerGridView.as_view(), name="charger_grid"),
    # Dashboard views
    path("buildings/", all_buildings_view, name="all_buildings_view"),
    path(
        "buildings/<int:building_id>/receivers/",
        single_building_view,
        name="single_building_view",
    ),
    path(
        "buildings/<int:building_id>/rooms/",
        rooms_in_building_view,
        name="rooms_in_building_view",
    ),
    path("rooms/", all_rooms_view, name="all_rooms_view"),
    path("rooms/<int:room_id>/receivers/", room_view, name="room_view"),
    path("device-type/<str:device_type>/", device_type_view, name="device_type_view"),
    path("priority/<str:priority>/", priority_view, name="priority_view"),
    path("performers/<int:performer_id>/", performer_view, name="performer_view"),
    # Assignment Management
    path("assignments/", AssignmentListView.as_view(), name="assignments"),
    path("assignments/rows/", AssignmentRowsView.as_view(), name="assignment_rows"),
    path("assignments/create/", create_assignment, name="create_assignment"),
    path("assignments/<int:pk>/update/", update_assignment, name="update_assignment"),
    path("assignments/<int:pk>/delete/", delete_assignment, name="delete_assignment"),
    # Settings management
    path("settings/", settings_overview, name="settings_overview"),
    path("settings/bulk/", BulkSettingConfigView.as_view(), name="settings_bulk_config"),
    path(
        "settings/manufacturer/",
        ManufacturerSettingsView.as_view(),
        name="settings_manufacturer_config",
    ),
    path("settings-diff/", settings_diff_view, name="settings_diff"),
    # Kiosk/Display Wall
    path("walls/", DisplayWallListView.as_view(), name="display_wall_list"),
    path("walls/<int:pk>/", DisplayWallDetailView.as_view(), name="display_wall_detail"),
    path("walls/<int:wall_id>/sections/", WallSectionListView.as_view(), name="wall_section_list"),
    path("walls/<int:wall_id>/data/", KioskDataView.as_view(), name="kiosk_data"),
    path("walls/<int:wall_id>/content/", KioskContentView.as_view(), name="kiosk_content"),
    path("walls/<int:wall_id>/health/", KioskHealthView.as_view(), name="kiosk_health"),
    path("kiosk/<str:kiosk_id>/", KioskAuthView.as_view(), name="kiosk_display"),
    # HTMX Partials
    path("partials/channel/<int:channel_id>/", channel_card_partial, name="channel_card_partial"),
    path("partials/charger-slot/<int:slot_id>/", charger_slot_partial, name="charger_slot_partial"),
    path(
        "partials/wall-section/<int:section_id>/", wall_section_partial, name="wall_section_partial"
    ),
    path("partials/alert/<int:alert_id>/", alert_row_partial, name="alert_row_partial"),
    path(
        "partials/assignment/<int:assignment_id>/",
        assignment_row_partial,
        name="assignment_row_partial",
    ),
    path("partials/charger-grid/", charger_grid_partial, name="charger_grid_partial"),
    path("partials/device-tiles/", device_tiles_partial, name="device_tiles_partial"),
]
