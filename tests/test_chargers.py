from django.test import RequestFactory, TestCase
from django.urls import reverse

from micboard.chargers.views import charger_display
from micboard.models import Building, Charger, ChargerSlot, Location


class ChargerDisplayViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.building = Building.objects.create(name="Test Building")
        self.location = Location.objects.create(name="Test Room", building=self.building)

    def test_charger_display_no_chargers(self):
        request = self.factory.get(reverse("micboard:charger_display"))
        response = charger_display(request)
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
        request = self.factory.get(reverse("micboard:charger_display"))
        response = charger_display(request)
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

        response = charger_display(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ULXD2")
        self.assertContains(response, "85%")
        # Check for the lightning bolt icon for charging
        self.assertContains(response, "bi-lightning-fill")
