from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from micboard.models.settings.registry import Setting, SettingDefinition

TEST_PASSWORD = "admin123"


class SettingsDiffAdminViewTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=TEST_PASSWORD
        )
        self.client = Client()

    def test_settings_diff_view_requires_staff(self):
        # Not logged in: should redirect to login
        response = self.client.get(reverse("micboard:settings_diff"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_settings_diff_view_as_admin(self):
        definition = SettingDefinition.objects.create(
            key="API_SECRET_KEY",
            label="API Secret",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default",
        )
        Setting.objects.create(definition=definition, value="global-value")
        Setting.objects.create(definition=definition, organization_id=1, value="org-secret")

        self.client.force_login(self.admin)
        response = self.client.get(reverse("micboard:settings_diff"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Settings Overrides Diff")
        self.assertContains(response, "API Secret")
        self.assertContains(response, "Org 1")
        self.assertContains(response, "••••••")

    def test_settings_overview_hides_stored_values(self):
        definition = SettingDefinition.objects.create(
            key="API_SECRET_KEY",
            label="API Secret",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default-secret",
        )
        Setting.objects.create(definition=definition, value="stored-super-secret")
        self.client.force_login(self.admin)

        response = self.client.get(reverse("micboard:settings_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Settings Overview")
        self.assertContains(response, "API Secret")
        self.assertContains(response, "API_SECRET_KEY")
        self.assertNotContains(response, "stored-super-secret")
        self.assertNotContains(response, "default-secret")

    def test_settings_management_routes_are_reversible_and_render(self):
        """Every documented settings endpoint must be reachable through the public URLconf."""
        self.client.force_login(self.admin)
        routes = {
            "micboard:settings_overview": "/settings/",
            "micboard:settings_bulk_config": "/settings/bulk/",
            "micboard:settings_manufacturer_config": "/settings/manufacturer/",
        }

        for route_name, expected_path in routes.items():
            with self.subTest(route_name=route_name):
                url = reverse(route_name)
                self.assertEqual(url, expected_path)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_settings_diff_masks_unknown_text_definitions(self):
        """Unknown values stay hidden regardless of name or scalar type."""
        credential_definition = SettingDefinition.objects.create(
            key="OAUTH_CREDENTIAL",
            label="OAuth Credential",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="credential-default",
        )
        pin_definition = SettingDefinition.objects.create(
            key="DOOR_PIN",
            label="Door PIN",
            setting_type=SettingDefinition.TYPE_INTEGER,
            default_value="1234",
        )
        Setting.objects.create(
            definition=credential_definition,
            organization_id=1,
            value="credential-value",
        )
        Setting.objects.create(
            definition=pin_definition,
            organization_id=1,
            value="9876",
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("micboard:settings_diff"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "••••••")
        self.assertNotContains(response, "credential-default")
        self.assertNotContains(response, "credential-value")
        self.assertNotContains(response, "1234")
        self.assertNotContains(response, "9876")
