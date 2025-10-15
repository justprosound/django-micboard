"""
Tests for alert management and email notifications.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from micboard.alerts import AlertManager, check_transmitter_alerts
from micboard.email import EmailService, send_alert_email, send_system_email
from micboard.models import Alert, Channel, DeviceAssignment, Receiver, Transmitter

User = get_user_model()

User = get_user_model()


class AlertManagerTest(TestCase):
    """Test AlertManager functionality"""

    def setUp(self):
        self.manager = AlertManager()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
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
            battery=80,
            audio_level=0,
            rf_level=-50,
        )
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            alert_on_battery_low=True,
            alert_on_signal_loss=True,
            alert_on_audio_low=True,
        )

    def test_check_battery_alerts_normal(self):
        """Test battery alerts when battery is normal"""
        self.transmitter.battery = 90  # Normal level
        self.transmitter.save()

        self.manager.check_transmitter_alerts(self.transmitter)

        # Should not create alert
        assert Alert.objects.count() == 0

    def test_check_battery_alerts_low(self):
        """Test battery alerts when battery is low"""
        self.transmitter.battery = 50  # Should give ~19% battery
        self.transmitter.save()

        self.manager.check_transmitter_alerts(self.transmitter)

        # Should create alert
        assert Alert.objects.count() == 1
        alert = Alert.objects.first()
        assert alert.alert_type == "battery_low"
        assert "Battery low:" in alert.message

    def test_check_battery_alerts_critical(self):
        """Test battery alerts when battery is critical"""
        self.transmitter.battery = 5  # Critical level
        self.transmitter.save()

        self.manager.check_transmitter_alerts(self.transmitter)

        # Should create alert
        assert Alert.objects.count() == 1
        alert = Alert.objects.first()
        assert alert.alert_type == "battery_critical"
        assert "Battery critically low: 5%" in alert.message

    def test_check_signal_alerts(self):
        """Test signal loss alerts"""
        self.transmitter.rf_level = -90  # Poor signal
        self.transmitter.save()

        self.manager.check_transmitter_alerts(self.transmitter)

        # Should create alert
        assert Alert.objects.count() == 1
        alert = Alert.objects.first()
        assert alert.alert_type == "signal_loss"
        assert "Signal loss detected" in alert.message

    def test_check_audio_alerts(self):
        """Test audio level alerts"""
        self.transmitter.audio_level = -50  # Low audio
        self.transmitter.save()

        self.manager.check_transmitter_alerts(self.transmitter)

        # Should create alert
        assert Alert.objects.count() == 1
        alert = Alert.objects.first()
        assert alert.alert_type == "audio_low"
        assert "Audio level too low" in alert.message

    def test_check_device_offline_alerts(self):
        """Test device offline alerts"""
        self.receiver.is_active = False
        self.receiver.save()

        self.manager.check_device_offline_alerts(self.channel)

        # Should create alert
        assert Alert.objects.count() == 1
        alert = Alert.objects.first()
        assert alert.alert_type == "device_offline"
        assert "Device offline" in alert.message

    def test_duplicate_alert_prevention(self):
        """Test that duplicate alerts are not created"""
        self.transmitter.battery = 15  # Low level
        self.transmitter.save()

        # First call should create alert
        self.manager.check_transmitter_alerts(self.transmitter)
        assert Alert.objects.count() == 1

        # Second call within 1 hour should not create another alert
        self.manager.check_transmitter_alerts(self.transmitter)
        assert Alert.objects.count() == 1

    def test_alert_acknowledgement(self):
        """Test alert acknowledgement"""
        self.transmitter.battery = 15
        self.transmitter.save()
        self.manager.check_transmitter_alerts(self.transmitter)

        alert = Alert.objects.first()
        assert alert.status == "pending"

        alert.acknowledge(self.user)
        alert.refresh_from_db()
        assert alert.status == "acknowledged"
        assert alert.acknowledged_at is not None

    def test_alert_resolution(self):
        """Test alert resolution"""
        self.transmitter.battery = 15
        self.transmitter.save()
        self.manager.check_transmitter_alerts(self.transmitter)

        alert = Alert.objects.first()
        alert.resolve()
        alert.refresh_from_db()
        assert alert.status == "resolved"
        assert alert.resolved_at is not None


class EmailServiceTest(TestCase):
    """Test EmailService functionality"""

    def setUp(self):
        self.service = EmailService()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
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
        self.alert = Alert.objects.create(
            channel=self.channel,
            user=self.user,
            alert_type="battery_low",
            message="Battery low: 15%",
            status="pending",
        )

    @override_settings(
        MICBOARD_CONFIG={
            "EMAIL_RECIPIENTS": ["admin@example.com"],
            "EMAIL_FROM": "micboard@example.com",
        }
    )
    def test_send_alert_notification_success(self):
        """Test successful alert email sending"""
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            result = self.service.send_alert_notification(self.alert)
            assert result is True

            # Check email was sent
            assert len(mail.outbox) == 1
            email = mail.outbox[0]
            assert "Micboard Alert: Battery Low" in email.subject
            assert "Battery low: 15%" in email.body
            assert email.from_email == "micboard@example.com"
            assert email.to == ["admin@example.com"]

    @override_settings(MICBOARD_CONFIG={})
    def test_send_alert_notification_no_recipients(self):
        """Test alert email sending with no recipients configured"""
        result = self.service.send_alert_notification(self.alert)
        assert result is False

    def test_send_system_notification(self):
        """Test system notification email sending"""
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            MICBOARD_CONFIG={
                "EMAIL_RECIPIENTS": ["admin@example.com"],
                "EMAIL_FROM": "micboard@example.com",
            },
        ):
            result = self.service.send_system_notification("Test Subject", "Test message body")
            assert result is True

            # Check email was sent
            assert len(mail.outbox) == 1
            email = mail.outbox[0]
            assert "Micboard System: Test Subject" in email.subject
            assert email.body == "Test message body"


class AlertEmailIntegrationTest(TestCase):
    """Test integration between alerts and email sending"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
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
            battery=10,  # Critical level
        )
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            alert_on_battery_low=True,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        MICBOARD_CONFIG={
            "EMAIL_RECIPIENTS": ["admin@example.com"],
            "EMAIL_FROM": "micboard@example.com",
        },
    )
    def test_alert_creation_sends_email(self):
        """Test that creating an alert automatically sends email"""
        # This would normally be called by the polling command
        check_transmitter_alerts(self.transmitter)

        # Should have created alert and sent email
        assert Alert.objects.count() == 1
        assert len(mail.outbox) == 1

    def test_convenience_functions(self):
        """Test convenience functions for alerts and emails"""
        # Test alert checking convenience function
        check_transmitter_alerts(self.transmitter)
        assert Alert.objects.count() == 1

        # Test email sending convenience function
        alert = Alert.objects.first()
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            MICBOARD_CONFIG={
                "EMAIL_RECIPIENTS": ["admin@example.com"],
                "EMAIL_FROM": "micboard@example.com",
            },
        ):
            result = send_alert_email(alert)
            assert result is True
            assert len(mail.outbox) == 1

        # Test system email convenience function
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            MICBOARD_CONFIG={
                "EMAIL_RECIPIENTS": ["admin@example.com"],
                "EMAIL_FROM": "micboard@example.com",
            },
        ):
            result = send_system_email("Test", "Message")
            assert result is True
            assert len(mail.outbox) == 2  # Two emails sent
