"""Model display, validation, audit, and relation-query contracts."""

from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.integrations import ManufacturerAPIServer
from micboard.models.locations.structure import Building, Location
from micboard.models.settings.registry import SettingDefinition
from tests.factories.audit import ConfigurationAuditLogFactory, ServiceSyncLogFactory
from tests.factories.discovery import (
    DiscoveredDeviceFactory,
    DiscoveryCIDRFactory,
    DiscoveryFQDNFactory,
    DiscoveryJobFactory,
    ManufacturerConfigurationFactory,
    ManufacturerFactory,
    MicboardConfigFactory,
)
from tests.factories.hardware import (
    AccessoryFactory,
    ChargerFactory,
    ChargerSlotFactory,
    DisplayWallFactory,
    WallSectionFactory,
    WirelessUnitFactory,
)
from tests.factories.locations import BuildingFactory, LocationFactory, RoomFactory
from tests.factories.monitoring import (
    AlertFactory,
    MonitoringGroupFactory,
    MonitoringGroupLocationFactory,
    PerformerAssignmentFactory,
    PerformerFactory,
    UserAlertPreferenceFactory,
)
from tests.factories.realtime import RealTimeConnectionFactory
from tests.factories.rf_coordination import (
    ExclusionZoneFactory,
    FrequencyBandFactory,
    RegulatoryDomainFactory,
)
from tests.factories.telemetry import (
    APIHealthLogFactory,
    WirelessUnitSampleFactory,
    WirelessUnitSessionFactory,
)
from tests.factories.users import UserProfileFactory, UserViewFactory


@pytest.mark.django_db
def test_sync_and_configuration_audit_display_and_duration() -> None:
    """Audit displays remain operator-readable and incomplete syncs report zero duration."""
    started = timezone.now()
    pending = ServiceSyncLogFactory(started_at=started, completed_at=None)
    complete = ServiceSyncLogFactory(
        started_at=started, completed_at=started + timedelta(seconds=9)
    )
    assert pending.duration_seconds() == 0
    assert complete.duration_seconds() == 9
    assert "Full Sync" in str(complete)

    configuration_log = ConfigurationAuditLogFactory()
    assert configuration_log.configuration.code in str(configuration_log)


@pytest.mark.django_db
def test_discovery_and_configuration_model_contracts() -> None:
    """Discovery models expose stable labels and reject incomplete configuration."""
    active = ManufacturerConfigurationFactory(is_active=True)
    inactive = ManufacturerConfigurationFactory(is_active=False)
    assert str(active).startswith("✓")
    assert str(inactive).startswith("✗")
    with pytest.raises(ValidationError, match="Code and name are required"):
        ManufacturerConfiguration(code="", name="").clean()

    with pytest.raises(ValidationError, match="Organization is required"):
        Building(name="Invalid", campus_id=2).clean()
    with (
        patch("micboard.models.locations.structure.apps.is_installed", return_value=False),
        pytest.raises(ValidationError, match="multitenancy app is not installed"),
    ):
        Building(name="Invalid", organization_id=1, campus_id=2).clean()
    with (
        patch("micboard.models.locations.structure.apps.is_installed", return_value=True),
        patch("micboard.multitenancy.models.Campus._default_manager.filter") as campuses,
    ):
        campuses.return_value.exists.return_value = True
        Building(name="Valid", organization_id=1, campus_id=2).clean()

    manufacturer = ManufacturerFactory()
    global_config = MicboardConfigFactory()
    vendor_config = MicboardConfigFactory(manufacturer=manufacturer)
    assert str(global_config).startswith("Global:")
    assert str(vendor_config).startswith(f"{manufacturer.name}:")
    assert manufacturer.name in str(DiscoveryCIDRFactory(manufacturer=manufacturer))
    assert manufacturer.name in str(DiscoveryFQDNFactory(manufacturer=manufacturer))
    assert manufacturer.name in str(DiscoveryJobFactory(manufacturer=manufacturer))

    discovered = DiscoveredDeviceFactory(manufacturer=manufacturer, status="ready")
    unowned = DiscoveredDeviceFactory(manufacturer=None, status="pending")
    assert manufacturer.name in str(discovered)
    assert "Pending (Not Ready)" in str(unowned)
    assert SettingDefinition(setting_type="unknown").parse_value("raw") == "raw"


@pytest.mark.django_db
def test_hardware_and_integration_display_contracts() -> None:
    """Hardware labels cover named, anonymous, occupied, and assignment states."""
    named = ChargerFactory(name="Stage Charger")
    anonymous = ChargerFactory(name="", model="SBC", serial_number="serial")
    assert str(named).startswith("Stage Charger")
    assert "Charger SBC" in str(anonymous)

    empty = ChargerSlotFactory(charger=named, occupied=False)
    occupied = ChargerSlotFactory(
        charger=anonymous,
        slot_number=2,
        occupied=True,
        device_model="ADX1",
        device_serial="unit-1",
    )
    assert "empty" in str(empty)
    assert "ADX1 unit-1" in str(occupied)

    wall = DisplayWallFactory(name="Stage", display_width_px=1920, display_height_px=1080)
    named_section = WallSectionFactory(wall=wall, name="Left")
    default_section = WallSectionFactory(wall=wall, name="")
    assert "1920x1080" in str(wall)
    assert str(named_section).endswith("Left")
    assert str(default_section).endswith("Default Section")
    wall.refresh_interval_seconds = type(wall).MIN_REFRESH_INTERVAL_SECONDS - 1
    with pytest.raises(ValidationError, match="Refresh interval must be between"):
        wall.clean()
    wall.refresh_interval_seconds = type(wall).MAX_REFRESH_INTERVAL_SECONDS + 1
    with pytest.raises(ValidationError, match="Refresh interval must be between"):
        wall.clean()
    wall.refresh_interval_seconds = type(wall).MIN_REFRESH_INTERVAL_SECONDS
    wall.clean()

    named_unit = WirelessUnitFactory(name="Lead")
    anonymous_unit = WirelessUnitFactory(name="", serial_number="bodypack-1", slot=2)
    assert str(named_unit).startswith("Lead")
    assert str(anonymous_unit).startswith("Unit bodypack-1")

    server = ManufacturerAPIServer(
        name="Venue API",
        manufacturer=ManufacturerAPIServer.Manufacturer.SHURE,
        base_url="https://api.example.test",
        shared_key="long-enough-key",
        location_name="Stage",
    )
    assert "Stage" in str(server)
    assert server.to_config_dict()["shared_key"] == "long-enough-key"
    with pytest.raises(ValidationError, match="at least 10"):
        ManufacturerAPIServer(shared_key="short").clean()

    assigned = AccessoryFactory(assigned_to="Lead", is_available=True)
    unavailable = AccessoryFactory(assigned_to="", is_available=False)
    assert "→ Lead" in str(assigned)
    assert str(unavailable).startswith("✗")


@pytest.mark.django_db
def test_location_monitoring_and_alert_model_contracts() -> None:
    """Location, performer, and alert labels cover optional relation state."""
    building = BuildingFactory(name="Venue")
    room = RoomFactory(building=building, name="Studio", floor="2")
    room_location = LocationFactory(building=building, room=room, name="Rack")
    open_location = LocationFactory(building=building, room=None, name="Lobby")
    assert str(building) == "Venue"
    assert str(room) == "Venue - Studio"
    assert str(room_location) == "Venue - Studio (Rack)"
    assert str(open_location) == "Venue (Lobby)"
    assert room_location.full_address == "Venue - Floor 2 - Studio"
    assert open_location.full_address == "Venue"
    with patch.object(Location, "building", None):
        assert Location(name="Fallback").full_address == "Fallback"

    group = MonitoringGroupFactory(name="Audio")
    link = MonitoringGroupLocationFactory(monitoring_group=group, location=room_location)
    assert str(group) == "Audio"
    assert str(link) == "Audio - Venue - Floor 2 - Studio"

    performer = PerformerFactory(name="Singer", title="Lead")
    untitled = PerformerFactory(name="Speaker", title="")
    assert str(performer) == "Singer (Lead)"
    assert str(untitled) == "Speaker"

    assignment = PerformerAssignmentFactory(
        performer=performer,
        monitoring_group=group,
        priority="critical",
    )
    assert "Singer" in str(assignment)
    assert list(performer.get_assigned_units()) == []
    assert list(performer.get_monitoring_groups()) == [group.pk]

    preference = UserAlertPreferenceFactory(quiet_hours_enabled=False)
    assert preference.user.username in str(preference)
    assert preference.is_quiet_hours(time(12)) is False
    preference.quiet_hours_enabled = True
    preference.quiet_hours_start = time(9)
    preference.quiet_hours_end = time(17)
    assert preference.is_quiet_hours(time(12)) is True
    preference.quiet_hours_start = time(22)
    preference.quiet_hours_end = time(7)
    assert preference.is_quiet_hours(time(23)) is True
    preference.quiet_hours_end = None
    assert preference.is_quiet_hours(time(23)) is False

    alert = AlertFactory()
    alert.created_at = timezone.now() - timedelta(hours=1)
    assert alert.alert_type in str(alert)
    assert alert.is_overdue is True
    alert.status = "resolved"
    assert alert.is_overdue is False
    alert.alert_type = "battery_critical"
    assert alert.severity == "High"
    alert.alert_type = "signal_loss"
    assert alert.severity == "Medium"
    alert.alert_type = "audio_low"
    assert alert.severity == "Low"


@pytest.mark.django_db
def test_telemetry_rf_user_and_realtime_contracts() -> None:
    """Remaining model labels and user accessibility queries stay executable."""
    domain = RegulatoryDomainFactory(code="FCC")
    band = FrequencyBandFactory(regulatory_domain=domain, name="UHF")
    zone = ExclusionZoneFactory(name="Tower")
    assert "FCC" in str(domain)
    assert "UHF" in str(band)
    assert "Tower" in str(zone)

    health = APIHealthLogFactory(status="healthy")
    session = WirelessUnitSessionFactory(is_active=True)
    ended = WirelessUnitSessionFactory(is_active=False)
    sample = WirelessUnitSampleFactory(session=session)
    assert "healthy" in str(health)
    assert "Session active" in str(session)
    assert "Session ended" in str(ended)
    assert "Sample" in str(sample)

    connection = RealTimeConnectionFactory(connection_type="sse", status="connected")
    assert "sse" in str(connection)

    profile = UserProfileFactory()
    profile.user.first_name = "Ada"
    profile.user.last_name = "Lovelace"
    profile.user.save(update_fields=["first_name", "last_name"])
    group = MonitoringGroupFactory()
    group.users.add(profile.user)
    assignment = PerformerAssignmentFactory(monitoring_group=group)
    assert "Ada Lovelace" in str(profile)
    assert list(profile.get_monitoring_groups()) == [group]
    assert list(profile.get_accessible_performers()) == [assignment.performer]
    assert list(profile.get_accessible_devices()) == [assignment.wireless_unit]

    view = UserViewFactory(user=profile.user, view_name="Stage")
    assert str(view) == f"{profile.user.username}'s view: Stage"
