"""Unit tests for WirelessUnit lifecycle hooks.

Tests the django-lifecycle hooks added to WirelessUnit model for:
- Status transition validation
- Automatic timestamp management
- Battery level monitoring
- Audit logging integration
"""

from unittest.mock import patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit


@pytest.fixture
def manufacturer(db):
    """Create a test manufacturer."""
    return Manufacturer.objects.create(
        name="Shure",
        code="shure",
    )


@pytest.fixture
def wireless_chassis(db, manufacturer):
    """Create a test wireless chassis."""
    return WirelessChassis.objects.create(
        manufacturer=manufacturer,
        name="Test Chassis",
        model="ULXD4Q",
        ip="192.168.1.100",
        status="online",
    )


@pytest.fixture
def wireless_unit(db, wireless_chassis):
    """Create a test wireless unit."""
    return WirelessUnit.objects.create(
        base_chassis=wireless_chassis,
        manufacturer=wireless_chassis.manufacturer,
        device_type="mic_transmitter",
        slot=1,
        model="ULXD2",
        serial_number="TEST001",
        name="Test Mic",
        status="discovered",
        battery=100,
    )


class TestWirelessUnitStatusTransitions:
    """Test status transition validation and lifecycle hooks."""

    def test_valid_transition_discovered_to_provisioning(self, wireless_unit):
        """Test valid transition from discovered to provisioning."""
        wireless_unit.status = "provisioning"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "provisioning"

    def test_valid_transition_provisioning_to_online(self, wireless_unit):
        """Test valid transition from provisioning to online."""
        wireless_unit.status = "provisioning"
        wireless_unit.save()

        wireless_unit.status = "online"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "online"

    def test_valid_transition_online_to_degraded(self, wireless_unit):
        """Test valid transition from online to degraded."""
        wireless_unit.status = "online"
        wireless_unit.save()

        wireless_unit.status = "degraded"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "degraded"

    def test_valid_transition_online_to_idle(self, wireless_unit):
        """Test valid transition from online to idle."""
        wireless_unit.status = "online"
        wireless_unit.save()

        wireless_unit.status = "idle"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "idle"

    def test_valid_transition_to_retired(self, wireless_unit):
        """Test valid transition from offline to retired."""
        wireless_unit.status = "offline"
        wireless_unit.save()

        wireless_unit.status = "retired"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "retired"

    def test_invalid_transition_discovered_to_online(self, wireless_unit):
        """Test invalid direct transition from discovered to online."""
        wireless_unit.status = "discovered"
        wireless_unit.save()

        wireless_unit.status = "online"
        with pytest.raises(ValueError, match="Invalid status transition"):
            wireless_unit.save()

    def test_invalid_transition_from_retired(self, wireless_unit):
        """Test that retired is a terminal state (no transitions out)."""
        wireless_unit.status = "retired"
        wireless_unit.save()

        wireless_unit.status = "online"
        with pytest.raises(ValueError, match="Invalid status transition"):
            wireless_unit.save()

    def test_invalid_transition_idle_to_provisioning(self, wireless_unit):
        """Test invalid transition from idle to provisioning."""
        wireless_unit.status = "idle"
        wireless_unit.save()

        wireless_unit.status = "provisioning"
        with pytest.raises(ValueError, match="Invalid status transition"):
            wireless_unit.save()


class TestWirelessUnitTimestampManagement:
    """Test automatic timestamp management via lifecycle hooks."""

    def test_last_seen_updated_on_online(self, wireless_unit):
        """Test last_seen is updated when unit goes online."""
        initial_last_seen = wireless_unit.last_seen
        wireless_unit.status = "online"
        wireless_unit.save()
        wireless_unit.refresh_from_db()

        assert wireless_unit.last_seen is not None
        if initial_last_seen:
            assert wireless_unit.last_seen > initial_last_seen

    def test_last_seen_updated_on_offline(self, wireless_unit):
        """Test last_seen is updated when unit goes offline."""
        wireless_unit.status = "online"
        wireless_unit.save()

        wireless_unit.status = "offline"
        wireless_unit.save()
        wireless_unit.refresh_from_db()

        assert wireless_unit.last_seen is not None


class TestWirelessUnitBatteryMonitoring:
    """Test battery level monitoring and logging."""

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_battery_drop_below_25_percent_logs(self, mock_log, wireless_unit):
        """Test that dropping below 25% triggers audit log."""
        wireless_unit.battery = 30
        wireless_unit.save()

        wireless_unit.battery = 20
        wireless_unit.save()

        assert mock_log.called
        call_args = mock_log.call_args
        assert call_args[1]["activity_type"] == "wireless_unit"
        assert call_args[1]["operation"] == "battery_warning"
        assert "battery: 20%" in call_args[1]["summary"]

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_battery_drop_below_15_percent_logs_warning(self, mock_log, wireless_unit):
        """Test that dropping below 15% triggers warning level audit log."""
        wireless_unit.battery = 20
        wireless_unit.save()

        wireless_unit.battery = 10
        wireless_unit.save()

        assert mock_log.called
        call_args = mock_log.call_args
        assert call_args[1]["level"] == "warning"

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_battery_unknown_value_no_log(self, mock_log, wireless_unit):
        """Test that unknown battery value (255) does not trigger logs."""
        wireless_unit.battery = 255
        wireless_unit.save()

        assert not mock_log.called

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_battery_increase_no_log(self, mock_log, wireless_unit):
        """Test that battery increasing does not trigger logs."""
        wireless_unit.battery = 20
        wireless_unit.save()
        mock_log.reset_mock()

        wireless_unit.battery = 30
        wireless_unit.save()

        assert not mock_log.called


class TestWirelessUnitAuditLogging:
    """Test audit logging integration via lifecycle hooks."""

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_status_change_logged_to_audit(self, mock_log, wireless_unit):
        """Test that all status changes are logged to audit service."""
        wireless_unit.status = "online"
        wireless_unit.save()

        assert mock_log.called
        call_args = mock_log.call_args
        assert call_args[1]["activity_type"] == "wireless_unit"
        assert call_args[1]["operation"] == "status_change"
        assert "discovered → online" in call_args[1]["summary"]
        assert call_args[1]["old_values"]["status"] == "discovered"
        assert call_args[1]["new_values"]["status"] == "online"

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_no_audit_log_when_status_unchanged(self, mock_log, wireless_unit):
        """Test that audit log is not triggered if status doesn't change."""
        wireless_unit.name = "Updated Name"
        wireless_unit.save()

        # Should have no status change logs
        status_change_calls = [
            call for call in mock_log.call_args_list if call[1]["operation"] == "status_change"
        ]
        assert len(status_change_calls) == 0


class TestWirelessUnitComplexWorkflows:
    """Test complex multi-step workflows."""

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_full_lifecycle_workflow(self, mock_log, wireless_unit):
        """Test a complete lifecycle: discovered → provisioning → online → offline → retired."""
        # Step 1: Provisioning
        wireless_unit.status = "provisioning"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "provisioning"

        # Step 2: Online
        wireless_unit.status = "online"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "online"
        assert wireless_unit.last_seen is not None

        # Step 3: Offline
        wireless_unit.status = "offline"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "offline"

        # Step 4: Retired
        wireless_unit.status = "retired"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "retired"

        # Verify audit logs for each transition
        assert mock_log.call_count >= 4

    @patch("micboard.models.hardware.wireless_unit.AuditService.log_activity")
    def test_maintenance_workflow(self, mock_log, wireless_unit):
        """Test maintenance workflow: online → maintenance → online."""
        wireless_unit.status = "online"
        wireless_unit.save()

        wireless_unit.status = "maintenance"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "maintenance"

        wireless_unit.status = "online"
        wireless_unit.save()
        wireless_unit.refresh_from_db()
        assert wireless_unit.status == "online"

        # Verify all transitions logged
        assert mock_log.call_count >= 3
