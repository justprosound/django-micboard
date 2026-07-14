"""Package and public API regression tests."""

from importlib.metadata import version
from importlib.util import find_spec

import micboard
import micboard.models as model_api
import micboard.models.telemetry.sessions as telemetry_sessions
import micboard.services as services
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager
from micboard.services.core.location import LocationService
from micboard.services.monitoring.connection import ConnectionHealthService


def test_runtime_version_uses_distribution_metadata() -> None:
    """Runtime and built-package versions must have one source of truth."""
    assert micboard.__version__ == version("django-micboard")


def test_removed_compatibility_names_are_not_public() -> None:
    """Removed aliases cannot silently return to public modules or service classes."""
    removed_service_exports = (
        "AccessControlService",
        "APIServerPollingService",
        "ConnectionError",
        "ConnectionHealthService",
        "DeviceAPIHealthChecker",
        "DeviceAPISyncService",
        "DeviceHealthService",
        "DeviceProbeService",
        "DiscoveryError",
        "HardwareLifecycleManager",
        "HardwareNotFoundError",
        "HardwareService",
        "HardwareSyncService",
        "LocationService",
        "LocationAlreadyExistsError",
        "LocationNotFoundError",
        "ManufacturerPluginError",
        "ManufacturerQueryService",
        "ManufacturerSyncService",
        "MicboardAPIError",
        "MicboardServiceError",
        "MonitoringService",
        "NormalizedHardware",
        "PaginatedResult",
        "PerformerAssignmentService",
        "PerformerService",
        "PollingService",
        "SyncResult",
        "filter_by_search",
        "get_lifecycle_manager",
        "get_polling_service",
        "paginate_queryset",
        "probe_device_ip",
    )
    for name in removed_service_exports:
        assert not hasattr(services, name)
    for name in ("TransmitterSession", "TransmitterSample"):
        assert not hasattr(telemetry_sessions, name)

    removed_model_exports = (
        "ActivityLog",
        "Alert",
        "Building",
        "Charger",
        "ChargerSlot",
        "ConfigurationAuditLog",
        "DeviceMovementLog",
        "DiscoveredDevice",
        "DiscoveryCIDR",
        "DiscoveryFQDN",
        "DiscoveryJob",
        "DiscoveryQueue",
        "DisplayWall",
        "ExclusionZone",
        "FrequencyBand",
        "Location",
        "Manufacturer",
        "ManufacturerAPIServer",
        "ManufacturerConfiguration",
        "MicboardConfig",
        "MonitoringGroup",
        "Performer",
        "PerformerAssignment",
        "RealTimeConnection",
        "RegulatoryDomain",
        "RFChannel",
        "Room",
        "ServiceSyncLog",
        "Setting",
        "SettingDefinition",
        "UserAlertPreference",
        "UserProfile",
        "UserView",
        "WallSection",
        "WirelessChassis",
        "WirelessUnit",
    )
    for name in removed_model_exports:
        assert not hasattr(model_api, name)

    assert not hasattr(HardwareLifecycleManager, "transition")
    assert not hasattr(ConnectionHealthService, "get_connections_for_manufacturer")
    assert not hasattr(ConnectionHealthService, "update_heartbeat")
    assert not hasattr(ConnectionHealthService, "is_connection_healthy")
    assert not hasattr(LocationService, "list_all_locations")


def test_removed_compatibility_modules_are_absent() -> None:
    """Old integration import paths must stay deleted instead of becoming shims."""
    assert find_spec("micboard.integrations.sennheiser.rate_limiter") is None
    assert find_spec("micboard.integrations.shure.discovery_sync") is None
