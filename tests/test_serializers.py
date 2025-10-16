"""
Tests for serializers in micboard.serializers.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from micboard.models import (
    Channel,
    DiscoveredDevice,
    Group,
    Manufacturer,
    Receiver,
    Transmitter,
)
from micboard.serializers import (
    serialize_channel,
    serialize_discovered_device,
    serialize_group,
    serialize_receiver,
    serialize_receiver_detail,
    serialize_receiver_summary,
    serialize_receivers,
    serialize_transmitter,
)


class TransmitterSerializerTest(TestCase):
    """Test the serialize_transmitter function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.transmitter = Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            battery=200,  # 78% battery
            battery_charge=80,
            audio_level=-20,
            rf_level=-50,
            frequency="512.125",
            antenna="A",
            tx_offset=0,
            quality=180,
            runtime="02:30:15",
            status="active",
            name="Test Transmitter",
            name_raw="TX-001",
        )

    def test_serialize_transmitter_basic(self):
        """Test basic transmitter serialization"""
        data = serialize_transmitter(self.transmitter)

        expected_keys = [
            "slot",
            "battery",
            "battery_charge",
            "battery_percentage",
            "audio_level",
            "rf_level",
            "frequency",
            "antenna",
            "tx_offset",
            "quality",
            "runtime",
            "status",
            "name",
            "name_raw",
            "updated_at",
        ]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["slot"], 1)
        self.assertEqual(data["battery"], 200)
        self.assertEqual(data["battery_charge"], 80)
        self.assertEqual(data["battery_percentage"], 78)  # 200 * 100 // 255
        self.assertEqual(data["audio_level"], -20)
        self.assertEqual(data["rf_level"], -50)
        self.assertEqual(data["frequency"], "512.125")
        self.assertEqual(data["antenna"], "A")
        self.assertEqual(data["tx_offset"], 0)
        self.assertEqual(data["quality"], 180)
        self.assertEqual(data["runtime"], "02:30:15")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["name"], "Test Transmitter")
        self.assertEqual(data["name_raw"], "TX-001")
        self.assertIsInstance(data["updated_at"], str)  # ISO format string

    def test_serialize_transmitter_with_extra(self):
        """Test transmitter serialization with extra properties"""
        data = serialize_transmitter(self.transmitter, include_extra=True)

        # Basic properties should still be there
        self.assertIn("slot", data)
        self.assertIn("battery", data)

        # Extra properties
        self.assertIn("battery_health", data)
        self.assertIn("signal_quality", data)
        self.assertIn("is_active", data)

        self.assertEqual(data["battery_health"], "good")  # > 50%
        self.assertEqual(data["signal_quality"], "good")  # > 150
        self.assertTrue(data["is_active"])  # Recently updated

    def test_serialize_transmitter_unknown_battery(self):
        """Test transmitter serialization with unknown battery"""
        self.transmitter.battery = 255  # UNKNOWN_BYTE_VALUE
        self.transmitter.save()

        data = serialize_transmitter(self.transmitter, include_extra=True)

        self.assertIsNone(data["battery_percentage"])
        self.assertEqual(data["battery_health"], "unknown")

    def test_serialize_transmitter_poor_signal(self):
        """Test transmitter serialization with poor signal quality"""
        self.transmitter.quality = 50  # Poor quality
        self.transmitter.save()

        data = serialize_transmitter(self.transmitter, include_extra=True)

        self.assertEqual(data["signal_quality"], "poor")

    def test_serialize_transmitter_inactive(self):
        """Test transmitter serialization when inactive"""
        # Set updated_at to old time using update to avoid auto_now
        old_time = timezone.now() - timedelta(minutes=10)
        Transmitter.objects.filter(pk=self.transmitter.pk).update(updated_at=old_time)
        self.transmitter.refresh_from_db()

        data = serialize_transmitter(self.transmitter, include_extra=True)

        self.assertFalse(data["is_active"])


class ChannelSerializerTest(TestCase):
    """Test the serialize_channel function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )

    def test_serialize_channel_without_transmitter(self):
        """Test channel serialization without transmitter"""
        data = serialize_channel(self.channel)

        self.assertEqual(data["channel_number"], 1)
        self.assertNotIn("transmitter", data)

    def test_serialize_channel_with_transmitter(self):
        """Test channel serialization with transmitter"""
        Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            battery=200,
            name="Test TX",
        )

        data = serialize_channel(self.channel)

        self.assertEqual(data["channel_number"], 1)
        self.assertIn("transmitter", data)
        self.assertEqual(data["transmitter"]["slot"], 1)
        self.assertEqual(data["transmitter"]["name"], "Test TX")

    def test_serialize_channel_with_extra(self):
        """Test channel serialization with extra transmitter details"""
        Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            battery=200,
            name="Test TX",
        )

        data = serialize_channel(self.channel, include_extra=True)

        self.assertIn("transmitter", data)
        self.assertIn("battery_health", data["transmitter"])
        self.assertIn("signal_quality", data["transmitter"])


class ReceiverSerializerTest(TestCase):
    """Test the serialize_receiver function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            firmware_version="1.2.3",
            is_active=True,
            last_seen=timezone.now(),
        )
        self.channel1 = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.channel2 = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
        )
        self.transmitter1 = Transmitter.objects.create(
            channel=self.channel1,
            slot=1,
            battery=200,
            name="TX1",
        )
        self.transmitter2 = Transmitter.objects.create(
            channel=self.channel2,
            slot=2,
            battery=150,
            name="TX2",
        )

    def test_serialize_receiver_basic(self):
        """Test basic receiver serialization"""
        data = serialize_receiver(self.receiver)

        expected_keys = [
            "api_device_id",
            "ip",
            "type",
            "name",
            "firmware",
            "is_active",
            "last_seen",
            "channels",
        ]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["api_device_id"], "test-device-001")
        self.assertEqual(data["ip"], "192.168.1.100")
        self.assertEqual(data["type"], "uhfr")
        self.assertEqual(data["name"], "Test Receiver")
        self.assertEqual(data["firmware"], "1.2.3")
        self.assertTrue(data["is_active"])
        self.assertIsInstance(data["last_seen"], str)  # ISO format
        self.assertEqual(len(data["channels"]), 2)

        # Check channels
        channel_nums = [ch["channel_number"] for ch in data["channels"]]
        self.assertEqual(sorted(channel_nums), [1, 2])

    def test_serialize_receiver_with_extra(self):
        """Test receiver serialization with extra properties"""
        data = serialize_receiver(self.receiver, include_extra=True)

        self.assertIn("health_status", data)
        self.assertEqual(data["health_status"], "healthy")  # Recently seen

    def test_serialize_receiver_inactive(self):
        """Test receiver serialization when inactive"""
        self.receiver.is_active = False
        self.receiver.save()

        data = serialize_receiver(self.receiver, include_extra=True)

        self.assertEqual(data["health_status"], "offline")

    def test_serialize_receiver_stale(self):
        """Test receiver serialization when stale"""
        old_time = timezone.now() - timedelta(hours=1)
        self.receiver.last_seen = old_time
        self.receiver.save()

        data = serialize_receiver(self.receiver, include_extra=True)

        self.assertEqual(data["health_status"], "stale")

    def test_serialize_receiver_no_last_seen(self):
        """Test receiver serialization with no last_seen"""
        self.receiver.last_seen = None
        self.receiver.save()

        data = serialize_receiver(self.receiver, include_extra=True)

        self.assertEqual(data["health_status"], "unknown")
        self.assertIsNone(data["last_seen"])


class ReceiversSerializerTest(TestCase):
    """Test the serialize_receivers function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver1 = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Receiver A",
            is_active=True,
        )
        self.receiver2 = Receiver.objects.create(
            api_device_id="test-device-002",
            manufacturer=self.manufacturer,
            ip="192.168.1.101",
            device_type="qlxd",
            name="Receiver B",
            is_active=True,
        )
        self.receiver3 = Receiver.objects.create(
            api_device_id="test-device-003",
            manufacturer=self.manufacturer,
            ip="192.168.1.102",
            device_type="ulxd",
            name="Receiver C",
            is_active=False,  # Inactive
        )

    def test_serialize_receivers_all_active(self):
        """Test serialize_receivers with default (active only)"""
        data = serialize_receivers()

        self.assertEqual(len(data), 2)  # Only active receivers
        names = [r["name"] for r in data]
        self.assertIn("Receiver A", names)
        self.assertIn("Receiver B", names)
        self.assertNotIn("Receiver C", names)

    def test_serialize_receivers_specific_list(self):
        """Test serialize_receivers with specific receiver list"""
        data = serialize_receivers([self.receiver1, self.receiver3])

        self.assertEqual(len(data), 2)
        names = [r["name"] for r in data]
        self.assertIn("Receiver A", names)
        self.assertIn("Receiver C", names)

    def test_serialize_receivers_with_extra(self):
        """Test serialize_receivers with extra properties"""
        data = serialize_receivers(include_extra=True)

        self.assertEqual(len(data), 2)
        for receiver_data in data:
            self.assertIn("health_status", receiver_data)

    def test_serialize_receivers_manufacturer_filtering(self):
        """Test serialize_receivers with manufacturer filtering"""
        # Create manufacturers
        manufacturer1 = Manufacturer.objects.create(
            code="shure",
            name="Shure Incorporated",
        )
        manufacturer2 = Manufacturer.objects.create(
            code="sennheiser",
            name="Sennheiser",
        )

        # Update receivers with manufacturers
        self.receiver1.manufacturer = manufacturer1
        self.receiver1.save()
        self.receiver2.manufacturer = manufacturer2
        self.receiver2.save()
        self.receiver3.manufacturer = manufacturer1
        self.receiver3.save()

        # Test filtering by manufacturer
        data = serialize_receivers(manufacturer_code="shure")

        self.assertEqual(len(data), 2)  # receiver1 and receiver3 (both active)
        names = [r["name"] for r in data]
        self.assertIn("Receiver A", names)
        self.assertNotIn("Receiver B", names)  # Different manufacturer
        self.assertIn("Receiver C", names)  # Even though inactive, should be included if specified

        # Check manufacturer code in serialized data
        for receiver_data in data:
            self.assertEqual(receiver_data["manufacturer_code"], "shure")

    def test_serialize_receivers_manufacturer_filtering_no_match(self):
        """Test serialize_receivers with manufacturer filtering when no receivers match"""
        # Create manufacturer but don't assign to receivers
        Manufacturer.objects.create(
            code="unknown",
            name="Unknown Manufacturer",
        )

        data = serialize_receivers(manufacturer_code="unknown")
        self.assertEqual(len(data), 0)


class DiscoveredDeviceSerializerTest(TestCase):
    """Test the serialize_discovered_device function"""

    def setUp(self):
        self.device = DiscoveredDevice.objects.create(
            ip="192.168.1.200",
            device_type="uhfr",
            channels=4,
        )

    def test_serialize_discovered_device(self):
        """Test discovered device serialization"""
        data = serialize_discovered_device(self.device)

        expected_keys = ["ip", "type", "channels", "discovered_at"]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["ip"], "192.168.1.200")
        self.assertEqual(data["type"], "uhfr")
        self.assertEqual(data["channels"], 4)
        self.assertIsInstance(data["discovered_at"], str)  # ISO format


class GroupSerializerTest(TestCase):
    """Test the serialize_group function"""

    def setUp(self):
        self.group = Group.objects.create(
            group_number=1,
            title="Test Group",
            slots=[1, 2, 3],
            hide_charts=True,
        )

    def test_serialize_group(self):
        """Test group serialization"""
        data = serialize_group(self.group)

        expected_keys = ["group", "title", "slots", "hide_charts"]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["group"], 1)
        self.assertEqual(data["title"], "Test Group")
        self.assertEqual(data["slots"], [1, 2, 3])
        self.assertTrue(data["hide_charts"])


class ReceiverSummarySerializerTest(TestCase):
    """Test the serialize_receiver_summary function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
            last_seen=timezone.now(),
        )
        # Add some channels
        Channel.objects.create(receiver=self.receiver, channel_number=1)
        Channel.objects.create(receiver=self.receiver, channel_number=2)

    def test_serialize_receiver_summary(self):
        """Test receiver summary serialization"""
        data = serialize_receiver_summary(self.receiver)

        expected_keys = [
            "api_device_id",
            "name",
            "device_type",
            "ip",
            "is_active",
            "health_status",
            "last_seen",
            "channel_count",
        ]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["api_device_id"], "test-device-001")
        self.assertEqual(data["name"], "Test Receiver")
        self.assertEqual(data["device_type"], "uhfr")
        self.assertEqual(data["ip"], "192.168.1.100")
        self.assertTrue(data["is_active"])
        self.assertEqual(data["health_status"], "healthy")
        self.assertEqual(data["channel_count"], 2)
        self.assertIsInstance(data["last_seen"], str)


class ReceiverDetailSerializerTest(TestCase):
    """Test the serialize_receiver_detail function"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            firmware_version="1.2.3",
            is_active=True,
            last_seen=timezone.now(),
        )
        self.channel1 = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.channel2 = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
        )
        self.transmitter1 = Transmitter.objects.create(
            channel=self.channel1,
            slot=1,
            battery=200,
            name="TX1",
        )
        # Channel 2 has no transmitter

    def test_serialize_receiver_detail(self):
        """Test detailed receiver serialization"""
        data = serialize_receiver_detail(self.receiver)

        expected_keys = [
            "api_device_id",
            "ip",
            "device_type",
            "name",
            "firmware_version",
            "is_active",
            "last_seen",
            "health_status",
            "is_healthy",
            "channel_count",
            "channels",
        ]

        for key in expected_keys:
            self.assertIn(key, data)

        self.assertEqual(data["api_device_id"], "test-device-001")
        self.assertEqual(data["name"], "Test Receiver")
        self.assertEqual(data["firmware_version"], "1.2.3")
        self.assertTrue(data["is_active"])
        self.assertEqual(data["health_status"], "healthy")
        self.assertTrue(data["is_healthy"])
        self.assertEqual(data["channel_count"], 2)
        self.assertEqual(len(data["channels"]), 2)

        # Check channels
        channels = {ch["channel_number"]: ch for ch in data["channels"]}
        self.assertIn(1, channels)
        self.assertIn(2, channels)

        # Channel 1 should have transmitter
        ch1 = channels[1]
        self.assertTrue(ch1["has_transmitter"])
        self.assertIn("transmitter", ch1)
        self.assertEqual(ch1["transmitter"]["slot"], 1)

        # Channel 2 should not have transmitter
        ch2 = channels[2]
        self.assertFalse(ch2["has_transmitter"])
        self.assertNotIn("transmitter", ch2)

    def test_serialize_receiver_detail_inactive(self):
        """Test detailed receiver serialization when inactive"""
        self.receiver.is_active = False
        self.receiver.save()

        data = serialize_receiver_detail(self.receiver)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["health_status"], "offline")
        self.assertFalse(data["is_healthy"])
