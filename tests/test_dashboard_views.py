"""
Tests for micboard dashboard views.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from micboard.models import DeviceAssignment, Group, Location, Receiver

User = get_user_model()


class IndexViewTest(TestCase):
    """Test index dashboard view"""

    def setUp(self):
        self.client = Client()

    def test_index_view_with_no_data(self):
        """Test index view when no devices or groups exist"""
        response = self.client.get("/")

        assert response.status_code == 200
        assert "micboard/index.html" in [template.name for template in response.templates]
        assert response.context["device_count"] == 0
        assert response.context["group_count"] == 0

    def test_index_view_with_data(self):
        """Test index view with devices and groups"""
        # Create test data
        Device.objects.create(
            ip="192.168.1.100",
            device_type="uhfr",
            channel=1,
            slot=1,
        )
        Device.objects.create(
            ip="192.168.1.101",
            device_type="uhfr",
            channel=1,
            slot=2,
            is_active=False,  # Inactive device should not be counted
        )
        Group.objects.create(
            group_number=1,
            title="Test Group 1",
            slots=[1, 2, 3],
        )
        Group.objects.create(
            group_number=2,
            title="Test Group 2",
            slots=[4, 5, 6],
        )

        response = self.client.get("/")

        assert response.status_code == 200
        assert "micboard/index.html" in [template.name for template in response.templates]
        assert response.context["device_count"] == 1  # Only active device
        assert response.context["group_count"] == 2


class AboutViewTest(TestCase):
    """Test about dashboard view"""

    def setUp(self):
        self.client = Client()

    def test_about_view(self):
        """Test about view renders correct template"""
        response = self.client.get("/about/")

        assert response.status_code == 200
        assert "micboard/about.html" in [template.name for template in response.templates]


class DeviceTypeViewTest(TestCase):
    """Test device type dashboard view"""

    def setUp(self):
        self.client = Client()
        self.device1 = Device.objects.create(
            ip="192.168.1.100", device_type="uhfr", channel=1, slot=1
        )
        self.device2 = Device.objects.create(
            ip="192.168.1.101", device_type="qlxd", channel=1, slot=2
        )
        self.device3 = Device.objects.create(
            ip="192.168.1.102", device_type="uhfr", channel=2, slot=3, is_active=False
        )

    def test_device_type_view_renders_correct_template_and_context(self):
        """Test device type view renders correct template and context"""
        response = self.client.get("/device-type/uhfr/")

        assert response.status_code == 200
        assert "micboard/device_type_view.html" in [
            template.name for template in response.templates
        ]
        assert response.context["device_type"] == "uhfr"
        assert list(response.context["devices"]) == [self.device1]

    def test_device_type_view_with_no_matching_devices(self):
        """Test device type view when no matching devices exist"""
        response = self.client.get("/device-type/ulxd/")

        assert response.status_code == 200
        assert "micboard/device_type_view.html" in [
            template.name for template in response.templates
        ]
        assert response.context["device_type"] == "ulxd"
        assert list(response.context["devices"]) == []


class BuildingViewTest(TestCase):
    """Test building dashboard view"""

    def setUp(self):
        self.client = Client()
        self.location1 = Location.objects.create(building="Building A", room="Room 101")
        self.location2 = Location.objects.create(building="Building B", room="Room 202")
        self.device1 = Device.objects.create(
            ip="192.168.1.100", device_type="uhfr", channel=1, slot=1
        )
        self.device2 = Device.objects.create(
            ip="192.168.1.101", device_type="qlxd", channel=1, slot=2
        )
        self.assignment1 = DeviceAssignment.objects.create(
            user=User.objects.create_user(username="testuser1"),
            device=self.device1,
            location=self.location1,
        )
        self.assignment2 = DeviceAssignment.objects.create(
            user=User.objects.create_user(username="testuser2"),
            device=self.device2,
            location=self.location1,
        )

    def test_building_view_renders_correct_template_and_context(self):
        """Test building view renders correct template and context"""
        response = self.client.get("/building/Building A/")

        assert response.status_code == 200
        assert "micboard/building_view.html" in [template.name for template in response.templates]
        assert response.context["building_name"] == "Building A"
        assert list(response.context["devices"]) == []


class UserViewTest(TestCase):
    """Test user dashboard view"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="testuser1")
        self.user2 = User.objects.create_user(username="testuser2")
        self.device1 = Device.objects.create(
            ip="192.168.1.100", device_type="uhfr", channel=1, slot=1
        )
        self.device2 = Device.objects.create(
            ip="192.168.1.101", device_type="qlxd", channel=1, slot=2
        )
        DeviceAssignment.objects.create(user=self.user1, device=self.device1)
        DeviceAssignment.objects.create(user=self.user1, device=self.device2)

    def test_user_view_renders_correct_template_and_context(self):
        """Test user view renders correct template and context"""
        response = self.client.get(f"/user/{self.user1.username}/")

        assert response.status_code == 200
        assert "micboard/user_view.html" in [template.name for template in response.templates]
        assert response.context["username"] == self.user1.username
        self.assertQuerysetEqual(
            response.context["devices"].order_by("slot"),
            [repr(self.device1), repr(self.device2)],
            transform=repr,
        )


class RoomViewTest(TestCase):
    """Test room dashboard view"""

    def setUp(self):
        self.client = Client()
        self.location1 = Location.objects.create(building="Building A", room="Room 101")
        self.location2 = Location.objects.create(building="Building B", room="Room 202")
        self.device1 = Device.objects.create(
            ip="192.168.1.100", device_type="uhfr", channel=1, slot=1
        )
        self.device2 = Device.objects.create(
            ip="192.168.1.101", device_type="qlxd", channel=1, slot=2
        )
        self.assignment1 = DeviceAssignment.objects.create(
            user=User.objects.create_user(username="testuser1"),
            device=self.device1,
            location=self.location1,
        )
        self.assignment2 = DeviceAssignment.objects.create(
            user=User.objects.create_user(username="testuser2"),
            device=self.device2,
            location=self.location1,
        )

    def test_room_view_renders_correct_template_and_context(self):
        """Test room view renders correct template and context"""
        response = self.client.get("/room/Room 101/")

        assert response.status_code == 200
        assert "micboard/room_view.html" in [template.name for template in response.templates]
        assert response.context["room_name"] == "Room 101"
        self.assertQuerysetEqual(
            response.context["devices"].order_by("slot"),
            [repr(self.device1), repr(self.device2)],
            transform=repr,
        )


class PriorityViewTest(TestCase):
    """Test priority dashboard view"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser")
        self.device1 = Device.objects.create(
            ip="192.168.1.100", device_type="uhfr", channel=1, slot=1
        )
        self.device2 = Device.objects.create(
            ip="192.168.1.101", device_type="qlxd", channel=1, slot=2
        )
        self.device3 = Device.objects.create(
            ip="192.168.1.102", device_type="ulxd", channel=1, slot=3
        )
        DeviceAssignment.objects.create(user=self.user, device=self.device1, priority="high")
        DeviceAssignment.objects.create(user=self.user, device=self.device2, priority="high")
        DeviceAssignment.objects.create(user=self.user, device=self.device3, priority="low")

    def test_priority_view_renders_correct_template_and_context(self):
        """Test priority view renders correct template and context"""
        response = self.client.get("/priority/high/")

        assert response.status_code == 200
        assert "micboard/priority_view.html" in [template.name for template in response.templates]
        assert response.context["priority"] == "high"
        self.assertQuerysetEqual(
            response.context["devices"].order_by("slot"),
            [repr(self.device1), repr(self.device2)],
            transform=repr,
        )

    def test_priority_view_with_no_matching_devices(self):
        """Test priority view when no matching devices exist"""
        response = self.client.get("/priority/critical/")

        assert response.status_code == 200
        assert "micboard/priority_view.html" in [template.name for template in response.templates]
        assert response.context["priority"] == "critical"
        assert list(response.context["devices"]) == []
