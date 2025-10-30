from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from micboard.admin.realtime import RealTimeConnectionAdmin
from micboard.models import Manufacturer, RealTimeConnection, Receiver

User = get_user_model()


class RealTimeConnectionAdminTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_site = admin.AdminSite()
        self.realtime_admin = RealTimeConnectionAdmin(RealTimeConnection, self.admin_site)

        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )

        self.manufacturer = Manufacturer.objects.create(name="Shure", code="shure")
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            ip="192.168.1.100",
            manufacturer=self.manufacturer,
            api_device_id="12345",
        )
        self.connection = RealTimeConnection.objects.create(
            receiver=self.receiver,
            connection_type="websocket",
            status="connected",
            connected_at=timezone.now() - timedelta(hours=1),
            last_message_at=timezone.now() - timedelta(minutes=5),
            error_count=0,
        )

    def test_status_colored(self):
        # Test connected status
        self.connection.status = "connected"
        self.connection.save()
        colored_status = self.realtime_admin.status_colored(self.connection)
        self.assertIn("green", colored_status)
        self.assertIn("Connected", colored_status)

        # Test disconnected status
        self.connection.status = "disconnected"
        self.connection.save()
        colored_status = self.realtime_admin.status_colored(self.connection)
        self.assertIn("gray", colored_status)
        self.assertIn("Disconnected", colored_status)

        # Test error status
        self.connection.status = "error"
        self.connection.save()
        colored_status = self.realtime_admin.status_colored(self.connection)
        self.assertIn("red", colored_status)
        self.assertIn("Error", colored_status)

        # Test connecting status
        self.connection.status = "connecting"
        self.connection.save()
        colored_status = self.realtime_admin.status_colored(self.connection)
        self.assertIn("orange", colored_status)
        self.assertIn("Connecting", colored_status)

        # Test stopped status
        self.connection.status = "stopped"
        self.connection.save()
        colored_status = self.realtime_admin.status_colored(self.connection)
        self.assertIn("blue", colored_status)
        self.assertIn("Stopped", colored_status)

    def test_connection_duration(self):
        # Test with a connection duration
        self.connection.connected_at = timezone.now() - timedelta(hours=2, minutes=30, seconds=15)
        self.connection.disconnected_at = None  # Ensure it calculates from now
        self.connection.save()
        duration = self.realtime_admin.connection_duration(self.connection)
        # The exact duration will vary slightly due to timezone.now(), so check format
        self.assertRegex(duration, r"\d{2}:\d{2}:\d{2}")

        # Test without a connection duration (disconnected_at is None and status is not disconnected)
        self.connection.connected_at = None
        self.connection.status = "connecting"
        self.connection.save()
        duration = self.realtime_admin.connection_duration(self.connection)
        self.assertEqual(duration, "-")

    def test_connection_duration_none(self):
        self.connection.connected_at = None
        self.connection.status = "disconnected"  # Ensure status is not "connected"
        self.connection.save()
        duration = self.realtime_admin.connection_duration(self.connection)
        self.assertEqual(duration, "-")

    def test_time_since_last_message(self):
        # Test with a time since last message
        self.connection.last_message_at = timezone.now() - timedelta(minutes=10, seconds=30)
        self.connection.save()
        time_since = self.realtime_admin.time_since_last_message(self.connection)
        self.assertRegex(time_since, r"\d{2}:\d{2}:\d{2}")

        # Test without a time since last message
        self.connection.last_message_at = None
        self.connection.save()
        time_since = self.realtime_admin.time_since_last_message(self.connection)
        self.assertEqual(time_since, "-")

    def test_mark_connected_action(self):
        request = self.factory.get("/")
        request.user = self.user
        queryset = RealTimeConnection.objects.filter(pk=self.connection.pk)

        self.realtime_admin.message_user = MagicMock()  # Mock message_user

        self.realtime_admin.mark_connected(request, queryset)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, "connected")
        self.assertIsNotNone(self.connection.connected_at)
        self.assertIsNotNone(self.connection.last_message_at)
        self.assertEqual(self.connection.error_count, 0)
        self.assertEqual(self.connection.error_message, "")
        self.realtime_admin.message_user.assert_called_once_with(
            request, "Marked 1 connection(s) as connected."
        )

    def test_mark_disconnected_action(self):
        request = self.factory.get("/")
        request.user = self.user
        queryset = RealTimeConnection.objects.filter(pk=self.connection.pk)

        self.realtime_admin.message_user = MagicMock()

        self.realtime_admin.mark_disconnected(request, queryset)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, "disconnected")
        self.assertIsNotNone(self.connection.disconnected_at)
        self.realtime_admin.message_user.assert_called_once_with(
            request, "Marked 1 connection(s) as disconnected."
        )

    def test_reset_error_count_action(self):
        self.connection.error_count = 5
        self.connection.error_message = "Some error"
        self.connection.save()

        request = self.factory.get("/")
        request.user = self.user
        queryset = RealTimeConnection.objects.filter(pk=self.connection.pk)

        self.realtime_admin.message_user = MagicMock()

        self.realtime_admin.reset_error_count(request, queryset)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.error_count, 0)
        self.assertEqual(self.connection.error_message, "")
        self.realtime_admin.message_user.assert_called_once_with(
            request, "Reset error count for 1 connection(s)."
        )

    def test_stop_connections_action(self):
        request = self.factory.get("/")
        request.user = self.user
        queryset = RealTimeConnection.objects.filter(pk=self.connection.pk)

        self.realtime_admin.message_user = MagicMock()

        self.realtime_admin.stop_connections(request, queryset)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, "stopped")
        self.assertIsNotNone(self.connection.disconnected_at)
        self.realtime_admin.message_user.assert_called_once_with(
            request, "Stopped 1 connection(s)."
        )

    def test_get_queryset(self):
        request = self.factory.get("/")
        request.user = self.user
        queryset = self.realtime_admin.get_queryset(request)
        # Check if select_related is used by trying to access a related field without hitting DB again
        # Expect 1 query to fetch RealTimeConnection and its related receiver and manufacturer
        with self.assertNumQueries(1):
            # Iterate and access related fields to ensure they are pre-fetched
            _ = [conn.receiver.name for conn in queryset]
        self.assertIn("receiver", queryset.query.select_related)
        self.assertIn("manufacturer", queryset.query.select_related["receiver"])
