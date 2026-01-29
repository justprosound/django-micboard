"""URL configuration for settings management views."""

from django.urls import path

from micboard.views.settings import (
    BulkSettingConfigView,
    ManufacturerSettingsView,
    settings_overview,
)

app_name = "settings"

urlpatterns = [
    path("", settings_overview, name="overview"),
    path("bulk/", BulkSettingConfigView.as_view(), name="bulk_config"),
    path("manufacturer/", ManufacturerSettingsView.as_view(), name="manufacturer_config"),
]
