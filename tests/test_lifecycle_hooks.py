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

from django.test import override_settings
from django.utils import timezone

import pytest

from micboard import model_lifecycle
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from micboard.services.hardware.dtos import ChassisDiscoveryCleanup


@pytest.mark.parametrize(
    ("receiver", "kwargs"),
    [
        (model_lifecycle._prepare_chassis, {"using": "default"}),
        (
            model_lifecycle._finish_chassis,
            {"created": True, "using": "default", "update_fields": None},
        ),
        (model_lifecycle._prepare_charger, {"using": "default"}),
        (model_lifecycle._prepare_unit, {}),
        (
            model_lifecycle._finish_unit,
            {"using": "default", "update_fields": None},
        ),
        (model_lifecycle._prepare_channel, {}),
        (
            model_lifecycle._finish_channel,
            {"using": "default", "update_fields": None},
        ),
        (model_lifecycle._prepare_building, {}),
        (model_lifecycle._prepare_manufacturer, {"using": "default"}),
        (
            model_lifecycle._finish_manufacturer,
            {"created": True, "using": "default"},
        ),
        (model_lifecycle._config_saved, {"using": "default"}),
        (model_lifecycle._registry_entry_changed, {"using": "default"}),
    ],
)
def test_save_lifecycle_adapters_ignore_raw_fixture_rows(receiver, kwargs) -> None:
    """Fixture deserialization must not validate, audit, or dispatch side effects."""
    # A bare object has no model fields, so any fixture-data access fails while
    # preserving Python's standard attribute-access contract.
    receiver(sender=object, instance=object(), raw=True, **kwargs)


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

    @patch("micboard.services.maintenance.audit.AuditService.log_activity")
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
        assert call_kwargs["using"] == "default"

    @patch("micboard.services.maintenance.audit.AuditService.log_activity")
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
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    )
    def test_status_change_broadcasted(
        self,
        mock_broadcast,
        chassis,
        django_capture_on_commit_callbacks,
    ):
        """Status changes should be broadcasted for real-time updates."""
        # Transition status
        with django_capture_on_commit_callbacks(execute=True):
            chassis.status = "provisioning"
            chassis.save()

        # Verify broadcast was called
        mock_broadcast.assert_called_once()
        call_kwargs = mock_broadcast.call_args.kwargs

        assert call_kwargs["device_id"] == chassis.pk
        assert call_kwargs["device_type"] == "WirelessChassis"
        assert call_kwargs["status"] == "provisioning"
        assert call_kwargs["is_active"] is False

    @patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    )
    def test_no_broadcast_when_status_unchanged(self, mock_broadcast, chassis):
        """No broadcast should occur when status doesn't change."""
        # Save without changing status
        chassis.name = "Updated Name"
        chassis.save()

        # Broadcast should not be called
        mock_broadcast.assert_not_called()


class TestDiscoveryScheduling:
    """Test that post-save discovery is submitted exactly once."""

    @override_settings(TESTING=True)
    @patch("micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin")
    def test_testing_mode_skips_remote_discovery_registration(self, mock_get_plugin, chassis):
        """Model factories must not write to manufacturer APIs during tests."""
        HardwarePostSaveHooks._add_ip_to_discovery(chassis)

        mock_get_plugin.assert_not_called()

    @override_settings(TESTING=False)
    @patch("micboard.utils.dependencies.enqueue_huey_task")
    @patch("micboard.utils.dependencies.huey_is_configured", return_value=True)
    @patch("micboard.tasks.sync.discovery.sync_receiver_discovery")
    def test_huey_discovery_is_enqueued_once(
        self,
        mock_sync_receiver_discovery,
        _mock_huey_is_configured,
        mock_enqueue_huey_task,
        chassis,
    ):
        from micboard.model_lifecycle import _dispatch_chassis_discovery

        _dispatch_chassis_discovery(chassis_id=chassis.pk, using="default")

        mock_enqueue_huey_task.assert_called_once_with(
            mock_sync_receiver_discovery,
            chassis.pk,
            using="default",
        )
        mock_sync_receiver_discovery.assert_not_called()

    @override_settings(TESTING=False)
    @patch("micboard.utils.dependencies.enqueue_huey_task")
    @patch("micboard.utils.dependencies.huey_is_configured", return_value=False)
    @patch("micboard.tasks.sync.discovery.sync_receiver_discovery")
    def test_unconfigured_huey_never_runs_discovery_inline(
        self,
        mock_sync_receiver_discovery,
        _mock_huey_is_configured,
        mock_enqueue_huey_task,
        chassis,
    ):
        from micboard.model_lifecycle import _dispatch_chassis_discovery

        _dispatch_chassis_discovery(chassis_id=chassis.pk, using="default")

        mock_enqueue_huey_task.assert_not_called()
        mock_sync_receiver_discovery.assert_not_called()

    @patch("micboard.services.sync.discovery_service.DiscoveryService.add_discovery_candidate")
    def test_discovery_task_preserves_database_alias(
        self,
        add_discovery_candidate,
        chassis,
    ):
        """Deferred discovery reads and checks inventory on the originating database."""
        from micboard.tasks.sync.discovery import sync_receiver_discovery

        sync_receiver_discovery(chassis.pk, using="default")

        add_discovery_candidate.assert_called_once_with(
            str(chassis.ip),
            chassis.manufacturer,
            source="chassis_save",
            using="default",
        )

    @override_settings(TESTING=False)
    @patch("micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin")
    def test_delete_cleanup_resolves_current_manufacturer_metadata(
        self,
        mock_get_plugin,
        manufacturer,
    ):
        """Cleanup snapshots retain IDs and resolve current vendor metadata after commit."""
        plugin = mock_get_plugin.return_value
        plugin.remove_discovery_ips.return_value = True
        target = ChassisDiscoveryCleanup(
            manufacturer_id=manufacturer.pk,
            ip="192.0.2.10",
        )

        HardwarePostSaveHooks._remove_ips_from_discovery(
            targets=(target,),
            using="default",
        )

        mock_get_plugin.assert_called_once_with(manufacturer.code, manufacturer)
        plugin.remove_discovery_ips.assert_called_once_with(["192.0.2.10"])


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
