"""Package and public API regression tests."""

import tomllib
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import micboard
import micboard.models as model_api
import micboard.models.telemetry.sessions as telemetry_sessions
import micboard.services as services
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_tooling_is_opt_in() -> None:
    """Runtime installs must not include the MkDocs documentation toolchain."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    runtime_dependencies = project["project"]["dependencies"]
    docs_dependencies = project["project"]["optional-dependencies"]["docs"]
    docs_packages = (
        "mkdocs-git-revision-date-localized-plugin",
        "mkdocs-material",
        "mkdocs-minify-plugin",
        "mkdocstrings[python]",
        "pymdown-extensions",
    )

    assert all(not dependency.startswith(docs_packages) for dependency in runtime_dependencies)
    assert all(
        any(dependency.startswith(package) for dependency in docs_dependencies)
        for package in docs_packages
    )


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
        "DeviceAPISyncService",
        "DeviceHealthService",
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


def test_removed_compatibility_modules_are_absent() -> None:
    """Old integration import paths must stay deleted instead of becoming shims."""
    assert find_spec("micboard.integrations.sennheiser.rate_limiter") is None
    assert find_spec("micboard.integrations.shure.discovery_sync") is None
    assert find_spec("micboard.services.monitoring.connection") is None
