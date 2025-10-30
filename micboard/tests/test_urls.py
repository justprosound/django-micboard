from django.test import TestCase
from django.urls import resolve, reverse

from micboard.views.dashboard import dashboard


class UrlsTest(TestCase):
    def test_index_url(self):
        url = reverse("index")
        self.assertEqual(resolve(url).func, dashboard.index)

    def test_all_buildings_url(self):
        url = reverse("all_buildings_view")
        self.assertEqual(resolve(url).func, dashboard.all_buildings_view)

    def test_single_building_url(self):
        url = reverse("single_building_view", args=["test_building"])
        self.assertEqual(resolve(url).func, dashboard.single_building_view)

    def test_room_url(self):
        url = reverse("room_view", args=["test_building", "test_room"])
        self.assertEqual(resolve(url).func, dashboard.room_view)

    def test_user_url(self):
        url = reverse("user_view", args=["test_user"])
        self.assertEqual(resolve(url).func, dashboard.user_view)

    def test_device_type_url(self):
        url = reverse("device_type_view", args=["test_type"])
        self.assertEqual(resolve(url).func, dashboard.device_type_view)

    def test_priority_url(self):
        url = reverse("priority_view", args=["test_priority"])
        self.assertEqual(resolve(url).func, dashboard.priority_view)
