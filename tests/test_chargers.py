from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.locations import Building, Location
from micboard.models.monitoring.group import MonitoringGroup


class ChargerDisplayViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="charger-test-user")
        self.building = Building.objects.create(name="Test Building")
        self.location = Location.objects.create(name="Test Room", building=self.building)
        group = MonitoringGroup.objects.create(name="Charger Test Group")
        group.users.add(self.user)
        group.locations.add(self.location)
        self.client.force_login(self.user)

    def test_charger_display_no_chargers(self):
        response = self.client.get(reverse("micboard:charger_display"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No charging stations found.")

    def test_charger_display_with_chargers(self):
        charger = Charger.objects.create(
            serial_number="CH1",
            name="Test Charger",
            location=self.location,
            is_active=True,
            status="online",
            order=1,
        )

        # Test with no slots first
        response = self.client.get(reverse("micboard:charger_display"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Charger")
        # Since slots are empty, it should say "No microphones" or similar if we have an else block
        # Actually in the template it checks {% if station.slots %}.
        # If there are NO slots in the DB for this charger, charger.slots.all() is empty.
        self.assertContains(response, "No microphones in this charging station.")

        # Now add slots
        ChargerSlot.objects.create(
            charger=charger,
            slot_number=1,
            occupied=True,
            device_model="ULXD2",
            battery_percent=85,
            device_status="charging",
        )

        response = self.client.get(reverse("micboard:charger_display"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ULXD2")
        self.assertContains(response, "85%")
        # Check for the lightning bolt icon for charging
        self.assertContains(response, "bi-lightning-fill")
