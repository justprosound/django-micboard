"""Keep domain packages free of convenience and compatibility exports."""

from __future__ import annotations

import importlib

import pytest

DOMAIN_EXPORTS = {
    "micboard.models.audit": ("ActivityLog", "ConfigurationAuditLog"),
    "micboard.models.discovery": ("Manufacturer", "DiscoveryJob"),
    "micboard.models.hardware": ("WirelessChassis", "WirelessUnit"),
    "micboard.models.locations": ("Building", "Location"),
    "micboard.models.monitoring": ("Alert", "MonitoringGroup"),
    "micboard.models.realtime": ("RealTimeConnection",),
    "micboard.models.rf_coordination": ("RFChannel", "RegulatoryDomain"),
    "micboard.models.settings": ("Setting", "SettingDefinition"),
    "micboard.models.telemetry": ("APIHealthLog", "WirelessUnitSample"),
    "micboard.models.users": ("UserProfile", "UserView"),
    "micboard.services.common.base": ("BaseHTTPClient", "ManufacturerPlugin"),
    "micboard.services.core": ("HardwareService", "PerformerAssignmentService"),
    "micboard.services.deduplication": ("DeduplicationResult", "check_device"),
    "micboard.services.hardware": ("prepare_chassis_for_save", "get_gap_analysis_summary"),
    "micboard.services.maintenance": ("AuditService", "EFISImportService"),
    "micboard.services.manufacturer": ("PluginRegistry", "ManufacturerSyncService"),
    "micboard.services.monitoring": ("AlertManager", "MonitoringService"),
    "micboard.services.notification": ("BroadcastService", "EmailService"),
    "micboard.services.settings": ("SettingsService", "settings"),
    "micboard.services.shared": ("ComplianceService", "SettingsRegistry"),
    "micboard.services.sync": ("DiscoveryService", "PollingService"),
    "micboard.views": ("about", "index"),
}


@pytest.mark.parametrize(("module_name", "removed_names"), DOMAIN_EXPORTS.items())
def test_domain_package_has_no_implementation_reexports(
    module_name: str,
    removed_names: tuple[str, ...],
) -> None:
    module = importlib.import_module(module_name)
    for name in removed_names:
        assert not hasattr(module, name)
