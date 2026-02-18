"""Unit tests for RFChannel lifecycle hooks.

Tests the django-lifecycle hooks added to RFChannel model for:
- Resource state transition validation
- Automatic state management when enabled/disabled
- Audit logging integration
"""

from unittest.mock import patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.rf_coordination.rf_channel import RFChannel


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
def rf_channel(db, wireless_chassis):
    """Create a test RF channel."""
    return RFChannel.objects.create(
        chassis=wireless_chassis,
        channel_number=1,
        link_direction="receive",
        protocol_family="ulxd",
        resource_state="free",
        enabled=True,
    )


class TestRFChannelResourceStateTransitions:
    """Test resource state transition validation."""

    def test_valid_transition_free_to_reserved(self, rf_channel):
        """Test valid transition from free to reserved."""
        rf_channel.resource_state = "reserved"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "reserved"

    def test_valid_transition_reserved_to_active(self, rf_channel):
        """Test valid transition from reserved to active."""
        rf_channel.resource_state = "reserved"
        rf_channel.save()

        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

    def test_valid_transition_active_to_degraded(self, rf_channel):
        """Test valid transition from active to degraded."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        rf_channel.resource_state = "degraded"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "degraded"

    def test_valid_transition_active_to_free(self, rf_channel):
        """Test valid transition from active back to free."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        rf_channel.resource_state = "free"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "free"

    def test_valid_transition_to_disabled(self, rf_channel):
        """Test valid transition from any state to disabled."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        rf_channel.resource_state = "disabled"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "disabled"

    def test_invalid_transition_free_to_degraded(self, rf_channel):
        """Test invalid direct transition from free to degraded."""
        rf_channel.resource_state = "free"
        rf_channel.save()

        rf_channel.resource_state = "degraded"
        with pytest.raises(ValueError, match="Invalid resource_state transition"):
            rf_channel.save()

    def test_invalid_transition_disabled_to_active(self, rf_channel):
        """Test invalid direct transition from disabled to active."""
        rf_channel.resource_state = "disabled"
        rf_channel.save()

        rf_channel.resource_state = "active"
        with pytest.raises(ValueError, match="Invalid resource_state transition"):
            rf_channel.save()

    def test_disabled_must_go_through_free(self, rf_channel):
        """Test that disabled state must transition back through free."""
        rf_channel.resource_state = "disabled"
        rf_channel.save()

        rf_channel.resource_state = "free"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "free"

        # Now can go to active
        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"


class TestRFChannelAutoDisableLogic:
    """Test automatic resource state management when enabled field changes."""

    def test_disabling_channel_sets_state_to_disabled(self, rf_channel):
        """Test that setting enabled=False automatically sets resource_state to disabled."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        rf_channel.enabled = False
        rf_channel.save()
        rf_channel.refresh_from_db()

        assert rf_channel.enabled is False
        assert rf_channel.resource_state == "disabled"

    def test_disabling_free_channel_sets_state_to_disabled(self, rf_channel):
        """Test that disabling a free channel sets state to disabled."""
        rf_channel.resource_state = "free"
        rf_channel.enabled = True
        rf_channel.save()

        rf_channel.enabled = False
        rf_channel.save()
        rf_channel.refresh_from_db()

        assert rf_channel.resource_state == "disabled"

    def test_enabling_channel_does_not_auto_change_state(self, rf_channel):
        """Test that enabling a channel does NOT automatically change resource_state."""
        rf_channel.resource_state = "disabled"
        rf_channel.enabled = False
        rf_channel.save()

        rf_channel.enabled = True
        rf_channel.save()
        rf_channel.refresh_from_db()

        # State should still be disabled - admin must manually set to free
        assert rf_channel.resource_state == "disabled"


class TestRFChannelAuditLogging:
    """Test audit logging integration via lifecycle hooks."""

    @patch("micboard.models.rf_coordination.rf_channel.AuditService.log_activity")
    def test_resource_state_change_logged_to_audit(self, mock_log, rf_channel):
        """Test that resource state changes are logged to audit service."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        assert mock_log.called
        call_args = mock_log.call_args
        assert call_args[1]["activity_type"] == "rf_channel"
        assert call_args[1]["operation"] == "resource_state_change"
        assert "free → active" in call_args[1]["summary"]
        assert call_args[1]["old_values"]["resource_state"] == "free"
        assert call_args[1]["new_values"]["resource_state"] == "active"

    @patch("micboard.models.rf_coordination.rf_channel.AuditService.log_activity")
    def test_no_audit_log_when_state_unchanged(self, mock_log, rf_channel):
        """Test that audit log is not triggered if resource_state doesn't change."""
        rf_channel.frequency = 500.0
        rf_channel.save()

        # Should have no resource state change logs
        state_change_calls = [
            call
            for call in mock_log.call_args_list
            if call[1]["operation"] == "resource_state_change"
        ]
        assert len(state_change_calls) == 0


class TestRFChannelComplexWorkflows:
    """Test complex multi-step workflows."""

    @patch("micboard.models.rf_coordination.rf_channel.AuditService.log_activity")
    def test_full_lifecycle_workflow(self, mock_log, rf_channel):
        """Test complete lifecycle: free → reserved → active → free."""
        # Step 1: Reserve
        rf_channel.resource_state = "reserved"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "reserved"

        # Step 2: Activate
        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

        # Step 3: Release
        rf_channel.resource_state = "free"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "free"

        # Verify audit logs for each transition
        assert mock_log.call_count >= 3

    @patch("micboard.models.rf_coordination.rf_channel.AuditService.log_activity")
    def test_degraded_recovery_workflow(self, mock_log, rf_channel):
        """Test degraded state recovery: active → degraded → active."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        rf_channel.resource_state = "degraded"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "degraded"

        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

        # Verify all transitions logged
        assert mock_log.call_count >= 3

    @patch("micboard.models.rf_coordination.rf_channel.AuditService.log_activity")
    def test_disable_and_reenable_workflow(self, mock_log, rf_channel):
        """Test disable and re-enable workflow."""
        rf_channel.resource_state = "active"
        rf_channel.save()

        # Disable
        rf_channel.enabled = False
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "disabled"

        # Re-enable and transition back to free
        rf_channel.enabled = True
        rf_channel.save()
        rf_channel.resource_state = "free"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "free"

        # Activate again
        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

        # Verify all transitions logged
        assert mock_log.call_count >= 4


class TestRFChannelLinkDirections:
    """Test resource state transitions work across all link directions."""

    def test_receive_link_state_transitions(self, wireless_chassis):
        """Test state transitions work for receive-direction links."""
        rf_channel = RFChannel.objects.create(
            chassis=wireless_chassis,
            channel_number=1,
            link_direction="receive",
            protocol_family="ulxd",
            resource_state="free",
        )

        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

    def test_send_link_state_transitions(self, wireless_chassis):
        """Test state transitions work for send-direction links."""
        rf_channel = RFChannel.objects.create(
            chassis=wireless_chassis,
            channel_number=2,
            link_direction="send",
            protocol_family="iem",
            resource_state="free",
        )

        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"

    def test_bidirectional_link_state_transitions(self, wireless_chassis):
        """Test state transitions work for bidirectional links."""
        rf_channel = RFChannel.objects.create(
            chassis=wireless_chassis,
            channel_number=3,
            link_direction="bidirectional",
            protocol_family="wmas",
            resource_state="free",
        )

        rf_channel.resource_state = "active"
        rf_channel.save()
        rf_channel.refresh_from_db()
        assert rf_channel.resource_state == "active"
