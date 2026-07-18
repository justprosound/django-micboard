"""Prevent forwarding functions and compatibility aliases from returning."""

from importlib.util import find_spec

import micboard.filters as filters
import micboard.multitenancy as multitenancy
from micboard.admin import receiver_inlines
from micboard.integrations.sennheiser.device_client import SennheiserDeviceClient
from micboard.integrations.shure.device_client import ShureDeviceClient
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.services.core import hardware_lifecycle
from micboard.services.core.device_metadata import SennheiserMetadataAccessor
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager, HardwareStatus
from micboard.services.core.hardware_sync import HardwareSyncService
from micboard.services.hardware import chassis_regulatory_service
from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService
from micboard.services.monitoring import alerts
from micboard.services.monitoring.base_health_mixin import HealthCheckMixin
from micboard.services.notification import email
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.notification.email_notification import EmailService
from micboard.services.notification.realtime_routing_service import RealtimeRoutingService
from micboard.services.settings.presentation_service import settings_presentation
from micboard.services.settings.registry import SettingsRegistry
from micboard.services.settings.visibility_service import settings_visibility
from micboard.services.sync import discovered_device_service
from micboard.websockets.consumers import MicboardConsumer


def test_forwarding_functions_and_aliases_are_absent() -> None:
    """Callers must use each implementation from its defining module."""
    assert not hasattr(filters, "HAS_DJANGO_FILTERS")
    assert not hasattr(email, "send_alert_email")
    assert not hasattr(email, "send_system_email")
    assert not hasattr(EmailService, "send_system_notification")
    assert not hasattr(BroadcastService, "broadcast_progress_update")
    assert not hasattr(MicboardConsumer, "progress_update")
    assert not hasattr(SennheiserMetadataAccessor, "get_hardware_version")
    assert not hasattr(SennheiserMetadataAccessor, "get_software_version")
    assert not hasattr(ChassisRefreshService, "refresh_ids")
    assert not hasattr(HealthCheckMixin, "is_degraded")
    assert not hasattr(HealthCheckMixin, "is_unhealthy")
    assert not hasattr(alerts, "check_transmitter_alerts")
    assert not hasattr(alerts, "check_hardware_offline_alerts")
    assert not hasattr(settings_visibility, "resolve_scope")
    assert not hasattr(settings_visibility, "matches_definition_scope")
    assert not hasattr(settings_presentation, "is_sensitive_definition")
    assert not hasattr(SettingsRegistry, "set")
    assert not hasattr(SettingsRegistry, "get_all_for_scope")
    assert not hasattr(chassis_regulatory_service, "get_regulatory_domain")
    assert not hasattr(multitenancy, "is_msp_enabled")
    assert not hasattr(multitenancy, "is_multisite_enabled")
    assert not hasattr(discovered_device_service, "get_device_metadata_accessor")
    assert not hasattr(hardware_lifecycle, "get_lifecycle_manager")
    assert not hasattr(HardwareStatus, "choices")
    assert not hasattr(HardwareStatus, "active_states")
    assert not hasattr(HardwareStatus, "inactive_states")
    for method_name in (
        "mark_discovered",
        "mark_degraded",
        "mark_maintenance",
        "mark_retired",
        "update_stale_devices",
        "create_with_state",
        "handle_poll_result",
        "handle_missing_device",
        "get_state_history",
    ):
        assert not hasattr(HardwareLifecycleManager, method_name)
    assert not hasattr(RealtimeRoutingService, "chassis_site_id")
    assert not hasattr(RealtimeRoutingService, "chassis_tenant_scope")
    assert not hasattr(HardwareSyncService, "sync_unit_battery")
    assert not hasattr(HardwareSyncService, "update_device_capabilities")
    assert not hasattr(HardwareSyncService, "async_sync_hardware_status")
    assert not hasattr(receiver_inlines, "WirelessUnitInline")


def test_noop_device_api_status_module_is_absent() -> None:
    """Do not retain importable placeholders or wildcard settings facades."""
    assert find_spec("micboard.services.core.device_api_status_sync") is None
    assert find_spec("micboard.settings.multitenancy") is None
    assert find_spec("micboard.services.shared.settings_registry") is None
    assert find_spec("micboard.multitenancy.feature_flags") is None
    assert find_spec("micboard.services.hardware.wireless_chassis_service") is None
    assert find_spec("micboard.services.chargers.charger_display_service") is None
    assert find_spec("micboard.chargers.views") is None
    assert find_spec("micboard.services.monitoring.connection_validation") is None


def test_unverified_vendor_enrichment_and_duplicate_polling_apis_are_absent() -> None:
    """Vendor clients expose only operations used by the production plugin contract."""
    for client_class in (ShureDeviceClient, SennheiserDeviceClient):
        for method_name in (
            "get_transmitter_data",
            "get_device_identity",
            "get_device_network",
            "get_device_status",
            "_enrich_device_data",
            "poll_all_devices",
        ):
            assert not hasattr(client_class, method_name)
    for method_name in ("get_device_identity", "get_device_network", "get_device_status"):
        assert not hasattr(ShurePlugin, method_name)
