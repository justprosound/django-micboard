"""Unit tests for WirelessChassis lifecycle hooks.

Tests the django-lifecycle integration for automatic state management:
- Status transition validation
- Timestamp management (online/offline)
- Audit logging
- Broadcast events
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis


@pytest.fixture
def manufacturer(db):
    """Create a test manufacturer."""
    return Manufacturer.objects.create(
        name="Test Manufacturer",
        code="test",
    )


@pytest.fixture
def chassis(manufacturer):
    """Create a test chassis in discovered state."""
    return WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="TEST-001",
        role="receiver",
        model="TEST-RX4",
        ip="192.168.1.100",
        status="discovered",
    )


@pytest.mark.django_db
class TestStatusTransitionValidation:
    """Test status transition validation hook."""

    def test_valid_transition_discovered_to_online(self, chassis):
        """Valid transition: discovered → provisioning → online."""
        # First transition: discovered → provisioning
        chassis.status = "provisioning"
        chassis.save()
        assert chassis.status == "provisioning"

        # Second transition: provisioning → online
        chassis.status = "online"
        chassis.save()
        assert chassis.status == "online"

    def test_invalid_transition_discovered_to_maintenance(self, chassis):
        """Invalid transition: discovered → maintenance should fail."""
        chassis.status = "maintenance"

        with pytest.raises(ValueError) as exc_info:
            chassis.save()

        assert "Invalid status transition" in str(exc_info.value)
        assert "discovered → maintenance" in str(exc_info.value)

    def test_terminal_state_retired(self, chassis):
        """Retired is a terminal state - no transitions allowed."""
        # Move to offline first (valid path to retired)
        chassis.status = "offline"
        chassis.save()

        # Move to retired
        chassis.status = "retired"
        chassis.save()
        assert chassis.status == "retired"

        # Try to transition out of retired (should fail)
        chassis.status = "online"

        with pytest.raises(ValueError) as exc_info:
            chassis.save()

        assert "none (terminal state)" in str(exc_info.value)

    def test_same_status_allowed(self, chassis):
        """Setting the same status should not trigger validation error."""
        chassis.status = "discovered"
        chassis.save()  # Should not raise
        assert chassis.status == "discovered"


@pytest.mark.django_db
class TestTimestampManagement:
    """Test automatic timestamp management hooks."""

    def test_last_online_at_set_on_online_transition(self, chassis):
        """last_online_at should be set when device goes online."""
        assert chassis.last_online_at is None
        assert chassis.is_online is False

        # Transition to online
        chassis.status = "provisioning"
        chassis.save()
        chassis.status = "online"
        chassis.save()

        # Refresh to get hook-updated values
        chassis.refresh_from_db()

        assert chassis.last_online_at is not None
        assert chassis.is_online is True

    def test_last_offline_at_set_on_offline_transition(self, chassis):
        """last_offline_at should be set when device goes offline."""
        # First go online
        chassis.status = "provisioning"
        chassis.save()
        chassis.status = "online"
        chassis.save()
        chassis.refresh_from_db()

        assert chassis.is_online is True

        # Now go offline
        chassis.status = "offline"
        chassis.save()
        chassis.refresh_from_db()

        assert chassis.last_offline_at is not None
        assert chassis.is_online is False

    def test_uptime_calculation_on_offline(self, chassis):
        """Total uptime should be calculated when device goes offline."""
        # Set up: device online with known last_online_at
        chassis.status = "provisioning"
        chassis.save()
        chassis.status = "online"
        chassis.save()
        chassis.refresh_from_db()

        # Simulate device being online for 10 minutes
        past_time = timezone.now() - timedelta(minutes=10)
        WirelessChassis.objects.filter(pk=chassis.pk).update(last_online_at=past_time)
        chassis.refresh_from_db()

        initial_uptime = chassis.total_uptime_minutes

        # Go offline
        chassis.status = "offline"
        chassis.save()
        chassis.refresh_from_db()

        # Uptime should have increased by ~10 minutes
        assert chassis.total_uptime_minutes >= initial_uptime + 9  # Allow some variance
        assert chassis.total_uptime_minutes <= initial_uptime + 11


@pytest.mark.django_db
class TestAuditLogging:
    """Test automatic audit logging hook."""

    @patch("micboard.models.hardware.wireless_chassis.AuditService.log_activity")
    def test_status_change_logged(self, mock_log_activity, chassis):
        """Status changes should be logged to audit system."""
        # Transition status
        chassis.status = "provisioning"
        chassis.save()

        # Verify audit log was called
        mock_log_activity.assert_called_once()
        call_kwargs = mock_log_activity.call_args.kwargs

        assert call_kwargs["activity_type"] == "hardware"
        assert call_kwargs["operation"] == "status_change"
        assert "discovered → provisioning" in call_kwargs["summary"]
        assert call_kwargs["obj"] == chassis
        assert call_kwargs["old_values"]["status"] == "discovered"
        assert call_kwargs["new_values"]["status"] == "provisioning"

    @patch("micboard.models.hardware.wireless_chassis.AuditService.log_activity")
    def test_no_log_when_status_unchanged(self, mock_log_activity, chassis):
        """No audit log should be created when status doesn't change."""
        # Save without changing status
        chassis.name = "Updated Name"
        chassis.save()

        # Audit should not be called
        mock_log_activity.assert_not_called()


@pytest.mark.django_db
class TestBroadcastEvents:
    """Test automatic broadcast hook."""

    @patch(
        "micboard.models.hardware.wireless_chassis.BroadcastService.broadcast_device_status_change"
    )
    def test_status_change_broadcasted(self, mock_broadcast, chassis):
        """Status changes should be broadcasted for real-time updates."""
        # Transition status
        chassis.status = "provisioning"
        chassis.save()

        # Verify broadcast was called
        mock_broadcast.assert_called_once()
        call_kwargs = mock_broadcast.call_args.kwargs

        assert call_kwargs["device"] == chassis
        assert call_kwargs["old_status"] == "discovered"
        assert call_kwargs["new_status"] == "provisioning"

    @patch(
        "micboard.models.hardware.wireless_chassis.BroadcastService.broadcast_device_status_change"
    )
    def test_no_broadcast_when_status_unchanged(self, mock_broadcast, chassis):
        """No broadcast should occur when status doesn't change."""
        # Save without changing status
        chassis.name = "Updated Name"
        chassis.save()

        # Broadcast should not be called
        mock_broadcast.assert_not_called()


@pytest.mark.django_db
class TestLifecycleStateFlows:
    """Test complete lifecycle state flows."""

    def test_complete_lifecycle_discovered_to_retired(self, chassis):
        """Test full lifecycle: discovered → provisioning → online → offline → retired."""
        assert chassis.status == "discovered"

        # Step 1: Provision
        chassis.status = "provisioning"
        chassis.save()
        assert chassis.status == "provisioning"

        # Step 2: Go online
        chassis.status = "online"
        chassis.save()
        chassis.refresh_from_db()
        assert chassis.status == "online"
        assert chassis.is_online is True

        # Step 3: Go offline
        chassis.status = "offline"
        chassis.save()
        chassis.refresh_from_db()
        assert chassis.status == "offline"
        assert chassis.is_online is False

        # Step 4: Retire
        chassis.status = "retired"
        chassis.save()
        assert chassis.status == "retired"

    def test_degraded_recovery_flow(self, chassis):
        """Test degraded state flow: online → degraded → online."""
        # Get to online state
        chassis.status = "provisioning"
        chassis.save()
        chassis.status = "online"
        chassis.save()
        chassis.refresh_from_db()

        # Degrade
        chassis.status = "degraded"
        chassis.save()
        assert chassis.status == "degraded"
        chassis.refresh_from_db()
        assert chassis.is_online is True  # Still considered online

        # Recover
        chassis.status = "online"
        chassis.save()
        assert chassis.status == "online"

    def test_maintenance_flow(self, chassis):
        """Test maintenance flow: online → maintenance → online."""
        # Get to online state
        chassis.status = "provisioning"
        chassis.save()
        chassis.status = "online"
        chassis.save()

        # Enter maintenance
        chassis.status = "maintenance"
        chassis.save()
        assert chassis.status == "maintenance"

        # Exit maintenance
        chassis.status = "online"
        chassis.save()
        assert chassis.status == "online"
