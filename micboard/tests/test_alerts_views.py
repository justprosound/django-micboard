from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time  # Added

from micboard.models import (
    Alert,
    Channel,
    DeviceAssignment,
    Manufacturer,
    Receiver,
    Transmitter,
    UserProfile,
)
from micboard.views.alerts import (
    AlertManager,
)

User = get_user_model()


class AlertManagerTest(TestCase):
    def setUp(self):
        self.alert_manager = AlertManager()
        self.manufacturer = Manufacturer.objects.create(name="Shure", code="shure")
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            ip="192.168.1.100",
            manufacturer=self.manufacturer,
            api_device_id="12345",
            status="online",
        )
        # Freeze time for consistent updated_at values
        with freeze_time(timezone.now()):
            self.channel = Channel.objects.create(
                receiver=self.receiver, channel_number=1, frequency=500.0
            )
            self.transmitter = Transmitter.objects.create(
                channel=self.channel,
                name="Test Transmitter",
                slot=1,
                battery=int(80 * Transmitter.UNKNOWN_BYTE_VALUE / 100),
                rf_level=-50,
                audio_level=-20,
                updated_at=timezone.now(),  # Set updated_at to make is_active True
            )
        self.user = User.objects.create_user(username="testuser", password="password")
        self.user_profile = UserProfile.objects.create(user=self.user)
        self.assignment = DeviceAssignment.objects.create(
            channel=self.channel,
            user=self.user,
            alert_on_battery_low=True,
            alert_on_signal_loss=True,
            alert_on_audio_low=True,
            alert_on_device_offline=True,
            is_active=True,
        )

    def test_get_channel_snapshot_with_transmitter(self):
        snapshot = self.alert_manager._get_channel_snapshot(self.channel)
        self.assertIn("receiver_name", snapshot)
        self.assertIn("transmitter_name", snapshot)
        self.assertEqual(snapshot["receiver_name"], self.receiver.name)
        self.assertEqual(snapshot["transmitter_name"], self.transmitter.name)

    def test_get_channel_snapshot_without_transmitter(self):
        self.transmitter.delete()  # Remove transmitter from channel
        self.channel.refresh_from_db()  # Add this line
        snapshot = self.alert_manager._get_channel_snapshot(self.channel)
        self.assertIn("receiver_name", snapshot)
        self.assertNotIn("transmitter_name", snapshot)

    @patch("micboard.views.alerts.send_alert_email")
    def test_create_alert_new_alert(self, mock_send_alert_email):
        alert = self.alert_manager._create_alert(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="test_type",
            message="Test message",
        )
        self.assertIsInstance(alert, Alert)
        self.assertEqual(alert.alert_type, "test_type")
        self.assertEqual(alert.message, "Test message")
        self.assertEqual(Alert.objects.count(), 1)
        mock_send_alert_email.assert_called_once_with(alert)

    @patch("micboard.views.alerts.send_alert_email")
    def test_create_alert_existing_alert(self, mock_send_alert_email):
        Alert.objects.create(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="test_type",
            message="Existing message",
            created_at=timezone.now() - timedelta(minutes=30),
        )
        alert = self.alert_manager._create_alert(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="test_type",
            message="New message",
        )
        self.assertEqual(Alert.objects.count(), 1)  # No new alert created
        self.assertEqual(alert.message, "Existing message")  # Returns existing alert
        mock_send_alert_email.assert_not_called()

    @patch("micboard.views.alerts.send_alert_email", side_effect=Exception("Email error"))
    def test_create_alert_email_failure(self, mock_send_alert_email):
        alert = self.alert_manager._create_alert(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="test_type",
            message="Test message",
        )
        alert.refresh_from_db()
        self.assertEqual(alert.status, "failed")
        mock_send_alert_email.assert_called_once()

    def test_check_battery_alerts_critical(self):
        self.transmitter.battery = int(
            5 * Transmitter.UNKNOWN_BYTE_VALUE / 100
        )  # Set battery field
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_battery_alerts(self.transmitter)
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args[1]["alert_type"], "battery_critical")

    def test_check_battery_alerts_low(self):
        self.transmitter.battery = int(
            15 * Transmitter.UNKNOWN_BYTE_VALUE / 100
        )  # Set battery field
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_battery_alerts(self.transmitter)
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args[1]["alert_type"], "battery_low")

    def test_check_battery_alerts_normal(self):
        self.transmitter.battery = int(
            50 * Transmitter.UNKNOWN_BYTE_VALUE / 100
        )  # Set battery field
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_battery_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_battery_alerts_no_battery_percentage(self):
        self.transmitter.battery = (
            Transmitter.UNKNOWN_BYTE_VALUE
        )  # Set battery to UNKNOWN_BYTE_VALUE
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_battery_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_battery_alerts_assignment_disabled(self):
        self.assignment.alert_on_battery_low = False
        self.assignment.save()
        self.transmitter.battery = int(
            5 * Transmitter.UNKNOWN_BYTE_VALUE / 100
        )  # Set battery field
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_battery_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_signal_alerts_loss(self):
        self.transmitter.rf_level = -90
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_signal_alerts(self.transmitter)
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args[1]["alert_type"], "signal_loss")

    def test_check_signal_alerts_normal(self):
        self.transmitter.rf_level = -40
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_signal_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_signal_alerts_assignment_disabled(self):
        self.assignment.alert_on_signal_loss = False
        self.assignment.save()
        self.transmitter.rf_level = -90
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_signal_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_audio_alerts_low(self):
        self.transmitter.audio_level = -60
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_audio_alerts(self.transmitter)
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args[1]["alert_type"], "audio_low")

    def test_check_audio_alerts_normal(self):
        self.transmitter.audio_level = -10
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_audio_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_audio_alerts_assignment_disabled(self):
        self.assignment.alert_on_audio_low = False
        self.assignment.save()
        self.transmitter.audio_level = -60
        self.transmitter.save()
        with patch.object(self.alert_manager, "_create_alert") as mock_create:
            self.alert_manager._check_audio_alerts(self.transmitter)
            mock_create.assert_not_called()

    def test_check_device_offline_alerts_receiver_offline(self):
        self.receiver.status = "offline"
        self.receiver.save()
        with patch.object(
            self.alert_manager, "_create_device_offline_alert"
        ) as mock_create_offline:
            self.alert_manager.check_device_offline_alerts(self.channel)
            mock_create_offline.assert_called_once_with(self.channel)

    @freeze_time("2025-10-30 12:00:00")  # Freeze time for this test
    def test_check_device_offline_alerts_transmitter_offline(self):
        self.receiver.status = "online"  # Ensure receiver is active
        self.receiver.save()
        # Set transmitter updated_at to be older than 5 minutes from frozen time
        Transmitter.objects.filter(pk=self.transmitter.pk).update(
            updated_at=timezone.now() - timedelta(minutes=10)
        )
        self.transmitter.refresh_from_db()
        self.channel.refresh_from_db()
        print(f"Transmitter updated_at: {self.transmitter.updated_at}")
        print(f"timezone.now(): {timezone.now()}")
        print(f"Transmitter is_active: {self.channel.transmitter.is_active}")  # Debug print
        with patch.object(
            self.alert_manager, "_create_device_offline_alert"
        ) as mock_create_offline:
            self.alert_manager.check_device_offline_alerts(self.channel)
            mock_create_offline.assert_called_once_with(self.channel)

    def test_check_device_offline_alerts_both_online(self):
        self.receiver.status = "online"
        self.receiver.save()
        # Make transmitter active by setting both status and last_seen
        self.transmitter.status = "online"
        self.transmitter.last_seen = timezone.now()
        self.transmitter.updated_at = timezone.now()
        self.transmitter.save()
        with patch.object(
            self.alert_manager, "_create_device_offline_alert"
        ) as mock_create_offline:
            self.alert_manager.check_device_offline_alerts(self.channel)
            mock_create_offline.assert_not_called()

    def test_check_transmitter_alerts(self):
        with patch.object(self.alert_manager, "_check_battery_alerts") as mock_battery:
            with patch.object(self.alert_manager, "_check_signal_alerts") as mock_signal:
                with patch.object(self.alert_manager, "_check_audio_alerts") as mock_audio:
                    self.alert_manager.check_transmitter_alerts(self.transmitter)
                    mock_battery.assert_called_once_with(self.transmitter)
                    mock_signal.assert_called_once_with(self.transmitter)
                    mock_audio.assert_called_once_with(self.transmitter)


class AlertsViewTest(TestCase):
    def setUp(self):
        self.client = Client()  # Use Client for view tests
        self.factory = RequestFactory()  # Keep RequestFactory for direct view calls if needed
        self.user = User.objects.create_user(username="testuser", password="password")
        self.manufacturer = Manufacturer.objects.create(name="Shure", code="shure")
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            ip="192.168.1.100",
            manufacturer=self.manufacturer,
            api_device_id="12345",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver, channel_number=1, frequency=500.0
        )
        self.assignment = DeviceAssignment.objects.create(
            channel=self.channel,
            user=self.user,
            is_active=True,
        )
        self.alert1 = Alert.objects.create(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="battery_low",
            message="Battery low",
            status="pending",
            created_at=timezone.now() - timedelta(days=1),
        )
        self.alert2 = Alert.objects.create(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="signal_loss",
            message="Signal loss",
            status="resolved",
            created_at=timezone.now() - timedelta(days=2),
        )

    def test_alerts_view_default(self):
        self.client.force_login(self.user)  # Login the user
        response = self.client.get(reverse("alerts"))  # Use client.get
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Battery low")
        self.assertNotContains(response, "Signal loss")  # Default filter is pending

    def test_alerts_view_all_status(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("alerts") + "?status=all")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Battery low")
        self.assertContains(response, "Signal loss")

    def test_alerts_view_filter_by_type(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("alerts") + "?status=all&type=signal_loss")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Battery low")
        self.assertContains(response, "Signal loss")

    def test_alert_detail_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("alert_detail", args=[self.alert1.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Battery low")

    def test_acknowledge_alert_view_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("acknowledge_alert", args=[self.alert1.id]))
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertEqual(response.url, reverse("alert_detail", args=[self.alert1.id]))

    def test_acknowledge_alert_view_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("acknowledge_alert", args=[self.alert1.id]))
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertEqual(response.url, reverse("alerts"))
        self.alert1.refresh_from_db()
        self.assertEqual(self.alert1.status, "acknowledged")

    def test_resolve_alert_view_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("resolve_alert", args=[self.alert1.id]))
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertEqual(response.url, reverse("alert_detail", args=[self.alert1.id]))

    def test_resolve_alert_view_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("resolve_alert", args=[self.alert1.id]))
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertEqual(response.url, reverse("alerts"))
        self.alert1.refresh_from_db()
        self.assertEqual(self.alert1.status, "resolved")
