"""
Tests for micboard models.
"""

from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from micboard.models import (
    Alert,
    Channel,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Location,
    MicboardConfig,
    MonitoringGroup,
    Receiver,
    Transmitter,
    UserAlertPreference,
)

User = get_user_model()


class ReceiverModelTest(TestCase):
    """Test Receiver model"""

    def setUp(self):
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            firmware_version="1.2.3",
        )

    def test_receiver_creation(self):
        """Test receiver can be created"""
        assert self.receiver.api_device_id == "test-device-001"
        assert self.receiver.ip == "192.168.1.100"
        assert self.receiver.device_type == "uhfr"
        assert self.receiver.name == "Test Receiver"
        assert self.receiver.firmware_version == "1.2.3"
        assert self.receiver.is_active

    def test_receiver_str(self):
        """Test receiver string representation"""
        expected = "uhfr - Test Receiver (192.168.1.100)"
        assert str(self.receiver) == expected

    def test_receiver_mark_online(self):
        """Test marking receiver as online"""
        self.receiver.is_active = False
        self.receiver.last_seen = None
        self.receiver.mark_online()
        assert self.receiver.is_active
        assert self.receiver.last_seen is not None

    def test_receiver_mark_offline(self):
        """Test marking receiver as offline"""
        self.receiver.is_active = True
        self.receiver.mark_offline()
        assert not self.receiver.is_active


class ChannelModelTest(TestCase):
    """Test Channel model"""

    def setUp(self):
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )

    def test_channel_creation(self):
        """Test channel can be created"""
        assert self.channel.receiver == self.receiver
        assert self.channel.channel_number == 1

    def test_channel_str(self):
        """Test channel string representation"""
        expected = "Test Receiver - Channel 1"
        assert str(self.channel) == expected

    def test_unique_channel_per_receiver(self):
        """Test that channel numbers are unique per receiver"""
        # This should work - different receiver
        receiver2 = Receiver.objects.create(
            api_device_id="test-device-002",
            ip="192.168.1.101",
            device_type="qlxd",
        )
        channel2 = Channel.objects.create(receiver=receiver2, channel_number=1)
        assert channel2.channel_number == 1

        # This should fail - same receiver, same channel
        with pytest.raises(IntegrityError):
            Channel.objects.create(receiver=self.receiver, channel_number=1)


class TransmitterModelTest(TestCase):
    """Test Transmitter model"""

    def setUp(self):
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.transmitter = Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            battery=75,
            audio_level=-10,
            rf_level=-50,
            frequency="518.125",
            status="OK",
        )

    def test_transmitter_creation(self):
        """Test transmitter can be created"""
        assert self.transmitter.channel == self.channel
        assert self.transmitter.slot == 1
        assert self.transmitter.battery == 75
        assert self.transmitter.audio_level == -10
        assert self.transmitter.rf_level == -50
        assert self.transmitter.frequency == "518.125"
        assert self.transmitter.status == "OK"

    def test_transmitter_str(self):
        """Test transmitter string representation"""
        expected = "Transmitter for Test Receiver - Channel 1 (Slot 1)"
        assert str(self.transmitter) == expected

    def test_battery_percentage(self):
        """Test battery percentage calculation"""
        # Normal battery level (75/255 ≈ 29%)
        assert self.transmitter.battery_percentage == 29

        # Unknown battery (255)
        self.transmitter.battery = 255
        assert self.transmitter.battery_percentage is None

        # Edge cases
        self.transmitter.battery = 0
        assert self.transmitter.battery_percentage == 0


class GroupModelTest(TestCase):
    """Test Group model"""

    def setUp(self):
        self.group = Group.objects.create(
            group_number=1,
            title="Test Group",
            slots=[1, 2, 3],
            hide_charts=False,
        )

    def test_group_creation(self):
        """Test group can be created"""
        assert self.group.group_number == 1
        assert self.group.title == "Test Group"
        assert self.group.slots == [1, 2, 3]
        assert not self.group.hide_charts

    def test_group_str(self):
        """Test group string representation"""
        expected = "Group 1: Test Group"
        assert str(self.group) == expected

    def test_get_channels(self):
        """Test getting channels in group"""
        receiver = Receiver.objects.create(
            api_device_id="test-device-001", ip="192.168.1.100", device_type="uhfr"
        )
        channel1 = Channel.objects.create(receiver=receiver, channel_number=1)
        channel2 = Channel.objects.create(receiver=receiver, channel_number=2)
        channel3 = Channel.objects.create(receiver=receiver, channel_number=3)

        Transmitter.objects.create(channel=channel1, slot=1)
        Transmitter.objects.create(channel=channel2, slot=2)
        Transmitter.objects.create(channel=channel3, slot=4)

        channels = self.group.get_channels()
        assert len(channels) == 2
        assert channels[0].slot == 1
        assert channels[1].slot == 2


class LocationModelTest(TestCase):
    """Test Location model"""

    def test_location_creation_simple(self):
        """Test location with simple fields"""
        location = Location.objects.create(
            name="Test Room",
            building="Test Building",
            room="101",
            floor="1",
        )
        assert location.name == "Test Room"
        assert location.building == "Test Building"
        assert location.room == "101"
        assert location.floor == "1"
        assert location.is_active

    def test_location_str_with_building_room(self):
        """Test location string with building and room"""
        location = Location.objects.create(
            name="Test Room",
            building="Test Building",
            room="101",
        )
        expected = "Test Building - 101"
        assert str(location) == expected

    def test_location_str_without_building_room(self):
        """Test location string without building/room"""
        location = Location.objects.create(name="Test Location")
        assert str(location) == "Test Location"

    def test_full_address(self):
        """Test full address property"""
        location = Location.objects.create(
            name="Test Room",
            building="Test Building",
            room="101",
            floor="1",
        )
        expected = "Test Building - Floor 1 - 101"
        assert location.full_address == expected


class MonitoringGroupModelTest(TestCase):
    """Test MonitoringGroup model"""

    def setUp(self):
        self.location = Location.objects.create(name="Test Location")
        self.user1 = User.objects.create_user(username="user1", email="user1@test.com")
        self.user2 = User.objects.create_user(username="user2", email="user2@test.com")

        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001", ip="192.168.1.100", device_type="uhfr"
        )
        self.channel1 = Channel.objects.create(receiver=self.receiver, channel_number=1)
        self.channel2 = Channel.objects.create(receiver=self.receiver, channel_number=2)

        self.group = MonitoringGroup.objects.create(
            name="Test Monitoring Group",
            location=self.location,
            description="Test description",
        )
        self.group.users.add(self.user1, self.user2)
        self.group.channels.add(self.channel1, self.channel2)

    def test_monitoring_group_creation(self):
        """Test monitoring group can be created"""
        assert self.group.name == "Test Monitoring Group"
        assert self.group.location == self.location
        assert self.group.description == "Test description"
        assert self.group.is_active

    def test_monitoring_group_str(self):
        """Test monitoring group string representation"""
        assert str(self.group) == "Test Monitoring Group"

    def test_get_active_users(self):
        """Test getting active users"""
        users = self.group.get_active_users()
        assert len(users) == 2
        assert self.user1 in users
        assert self.user2 in users

    def test_get_active_channels(self):
        """Test getting active channels"""
        channels = self.group.get_active_channels()
        assert len(channels) == 2
        assert self.channel1 in channels
        assert self.channel2 in channels


class DeviceAssignmentModelTest(TestCase):
    """Test DeviceAssignment model"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@test.com")
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        self.channel = Channel.objects.create(receiver=self.receiver, channel_number=1)
        self.location = Location.objects.create(name="Test Location")
        self.monitoring_group = MonitoringGroup.objects.create(name="Test Group")

        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            location=self.location,
            monitoring_group=self.monitoring_group,
            priority="high",
            notes="Test assignment",
        )

    def test_assignment_creation(self):
        """Test assignment can be created"""
        assert self.assignment.user == self.user
        assert self.assignment.channel == self.channel
        assert self.assignment.location == self.location
        assert self.assignment.monitoring_group == self.monitoring_group
        assert self.assignment.priority == "high"
        assert self.assignment.notes == "Test assignment"
        assert self.assignment.is_active

    def test_assignment_str(self):
        """Test assignment string representation"""
        expected = "testuser -> Test Receiver - Channel 1 (high)"
        assert str(self.assignment) == expected

    def test_unique_constraint(self):
        """Test unique constraint on user-channel pairs"""
        with pytest.raises(IntegrityError):
            DeviceAssignment.objects.create(
                user=self.user,
                channel=self.channel,
                priority="normal",
            )

    def test_get_alert_preferences(self):
        """Test getting alert preferences"""
        preferences = self.assignment.get_alert_preferences()
        expected = {
            "battery_low": True,
            "signal_loss": True,
            "audio_low": False,
            "device_offline": True,
        }
        assert preferences == expected


class UserAlertPreferenceModelTest(TestCase):
    """Test UserAlertPreference model"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@test.com")
        self.preference = UserAlertPreference.objects.create(
            user=self.user,
            notification_method="both",
            email_address="alerts@test.com",
            battery_low_threshold=25,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
        )

    def test_preference_creation(self):
        """Test preference can be created"""
        assert self.preference.user == self.user
        assert self.preference.notification_method == "both"
        assert self.preference.email_address == "alerts@test.com"
        assert self.preference.battery_low_threshold == 25
        assert self.preference.quiet_hours_enabled
        assert self.preference.quiet_hours_start == time(22, 0)
        assert self.preference.quiet_hours_end == time(8, 0)

    def test_preference_str(self):
        """Test preference string representation"""
        expected = "Alert preferences for testuser"
        assert str(self.preference) == expected

    def test_is_quiet_hours(self):
        """Test quiet hours checking"""
        # During quiet hours (23:00)
        quiet_time = time(23, 0)
        assert self.preference.is_quiet_hours(quiet_time)

        # Outside quiet hours (12:00)
        normal_time = time(12, 0)
        assert not self.preference.is_quiet_hours(normal_time)

        # At start boundary
        assert self.preference.is_quiet_hours(time(22, 0))

        # At end boundary
        assert self.preference.is_quiet_hours(time(8, 0))

    def test_is_quiet_hours_disabled(self):
        """Test quiet hours when disabled"""
        self.preference.quiet_hours_enabled = False
        assert not self.preference.is_quiet_hours(time(23, 0))


class AlertModelTest(TestCase):
    """Test Alert model"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@test.com")
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        self.channel = Channel.objects.create(receiver=self.receiver, channel_number=1)
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
        )

        self.alert = Alert.objects.create(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="battery_low",
            status="pending",
            message="Battery is low",
        )

    def test_alert_creation(self):
        """Test alert can be created"""
        assert self.alert.channel == self.channel
        assert self.alert.user == self.user
        assert self.alert.assignment == self.assignment
        assert self.alert.alert_type == "battery_low"
        assert self.alert.status == "pending"
        assert self.alert.message == "Battery is low"

    def test_alert_str(self):
        """Test alert string representation"""
        expected = "battery_low - Test Receiver - Channel 1 (pending)"
        assert str(self.alert) == expected

    def test_acknowledge_alert(self):
        """Test acknowledging an alert"""
        self.alert.acknowledge(self.user)
        assert self.alert.status == "acknowledged"
        assert self.alert.acknowledged_at is not None

    def test_resolve_alert(self):
        """Test resolving an alert"""
        self.alert.resolve()
        assert self.alert.status == "resolved"
        assert self.alert.resolved_at is not None

    def test_is_overdue(self):
        """Test overdue alert detection"""
        # Recent alert should not be overdue
        assert not self.alert.is_overdue

        # Make alert old
        old_time = timezone.now() - timezone.timedelta(minutes=35)
        self.alert.created_at = old_time
        self.alert.save()
        assert self.alert.is_overdue


class MicboardConfigModelTest(TestCase):
    """Test MicboardConfig model"""

    def test_config_creation(self):
        """Test config can be created"""
        config = MicboardConfig.objects.create(
            key="test_key",
            value="test_value",
        )
        assert config.key == "test_key"
        assert config.value == "test_value"

    def test_config_str(self):
        """Test config string representation"""
        config = MicboardConfig.objects.create(
            key="test_key",
            value="test_value",
        )
        expected = "test_key: test_value"
        assert str(config) == expected


class DiscoveredDeviceModelTest(TestCase):
    """Test DiscoveredDevice model"""

    def test_discovered_device_creation(self):
        """Test discovered device can be created"""
        device = DiscoveredDevice.objects.create(
            ip="192.168.1.100",
            device_type="uhfr",
            channels=2,
        )
        assert device.ip == "192.168.1.100"
        assert device.device_type == "uhfr"
        assert device.channels == 2

    def test_discovered_device_str(self):
        """Test discovered device string representation"""
        device = DiscoveredDevice.objects.create(
            ip="192.168.1.100",
            device_type="uhfr",
            channels=2,
        )
        expected = "uhfr at 192.168.1.100"
        assert str(device) == expected
