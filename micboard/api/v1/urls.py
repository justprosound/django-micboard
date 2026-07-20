from typing import Any
from rest_framework.routers import DefaultRouter

from micboard.api.v1.discovery import DiscoveredDeviceViewSet
from micboard.api.v1.hardware import RFChannelViewSet, WirelessChassisViewSet, WirelessUnitViewSet
from micboard.api.v1.monitoring import AlertViewSet, MonitoringGroupViewSet
from micboard.api.v1.settings import SettingDefinitionViewSet, SettingViewSet

router = DefaultRouter()
router.register(r"chassis", WirelessChassisViewSet, basename="chassis")
router.register(r"units", WirelessUnitViewSet, basename="units")
router.register(r"channels", RFChannelViewSet, basename="channels")
router.register(r"discovery", DiscoveredDeviceViewSet, basename="discovery")
router.register(r"monitoring/groups", MonitoringGroupViewSet, basename="monitoring-group")
router.register(r"monitoring/alerts", AlertViewSet, basename="alert")
router.register(r"settings/definitions", SettingDefinitionViewSet, basename="settingdefinition")
router.register(r"settings/overrides", SettingViewSet, basename="setting")

urlpatterns = router.urls
