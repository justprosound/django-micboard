from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class SettingsDiffAdminViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin123"
        )
        self.client = Client()

    def test_settings_diff_view_requires_staff(self):
        # Not logged in: should redirect to login
        response = self.client.get(reverse("micboard:settings_diff_stub"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_settings_diff_view_as_admin(self):
        self.client.login(username="admin", password="admin123")
        response = self.client.get(reverse("micboard:settings_diff_stub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Settings Overrides Diff")
        self.assertContains(response, "TODO:")
