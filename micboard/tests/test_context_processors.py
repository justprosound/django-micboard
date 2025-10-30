from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from micboard.context_processors import api_health
from micboard.models import Manufacturer


class APIHealthContextProcessorTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")
        cache.clear()  # Clear cache before each test

    def test_api_health_no_manufacturers(self):
        # Ensure no manufacturers exist
        Manufacturer.objects.all().delete()

        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "unconfigured")
        self.assertEqual(result["api_health"]["total_manufacturers"], 0)
        self.assertEqual(result["api_health"]["healthy_manufacturers"], 0)
        self.assertEqual(len(result["api_health"]["details"]), 0)

    @patch("micboard.models.Manufacturer.get_plugin_class")
    def test_api_health_all_healthy(self, mock_get_manufacturer_plugin):
        _manufacturer1 = Manufacturer.objects.create(name="Shure", code="shure", is_active=True)
        _manufacturer2 = Manufacturer.objects.create(
            name="Sennheiser", code="sennheiser", is_active=True
        )

        mock_plugin_instance = MagicMock()
        mock_plugin_instance.check_health.return_value = {"status": "healthy"}
        mock_get_manufacturer_plugin.return_value.return_value = mock_plugin_instance

        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "healthy")
        self.assertEqual(result["api_health"]["total_manufacturers"], 2)
        self.assertEqual(result["api_health"]["healthy_manufacturers"], 2)
        self.assertEqual(len(result["api_health"]["details"]), 2)
        self.assertEqual(result["api_health"]["details"][0]["status"], "healthy")
        self.assertEqual(result["api_health"]["details"][1]["status"], "healthy")

    @patch("micboard.models.Manufacturer.get_plugin_class")
    def test_api_health_some_unhealthy(self, mock_get_manufacturer_plugin):
        _manufacturer1 = Manufacturer.objects.create(name="Shure", code="shure", is_active=True)
        _manufacturer2 = Manufacturer.objects.create(
            name="Sennheiser", code="sennheiser", is_active=True
        )

        mock_plugin_instance1 = MagicMock()
        mock_plugin_instance1.check_health.return_value = {"status": "healthy"}

        mock_plugin_instance2 = MagicMock()
        mock_plugin_instance2.check_health.return_value = {"status": "unhealthy"}

        # Configure the mock to return different instances for different calls
        mock_get_manufacturer_plugin.side_effect = [
            MagicMock(return_value=mock_plugin_instance1),
            MagicMock(return_value=mock_plugin_instance2),
        ]

        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "partial")
        self.assertEqual(result["api_health"]["total_manufacturers"], 2)
        self.assertEqual(result["api_health"]["healthy_manufacturers"], 1)
        self.assertEqual(len(result["api_health"]["details"]), 2)
        self.assertEqual(result["api_health"]["details"][0]["status"], "healthy")
        self.assertEqual(result["api_health"]["details"][1]["status"], "unhealthy")

    @patch("micboard.models.Manufacturer.get_plugin_class")
    def test_api_health_all_unhealthy(self, mock_get_manufacturer_plugin):
        _manufacturer1 = Manufacturer.objects.create(name="Shure", code="shure", is_active=True)

        mock_plugin_instance = MagicMock()
        mock_plugin_instance.check_health.return_value = {"status": "unhealthy"}
        mock_get_manufacturer_plugin.return_value.return_value = mock_plugin_instance

        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "unhealthy")
        self.assertEqual(result["api_health"]["total_manufacturers"], 1)
        self.assertEqual(result["api_health"]["healthy_manufacturers"], 0)
        self.assertEqual(len(result["api_health"]["details"]), 1)
        self.assertEqual(result["api_health"]["details"][0]["status"], "unhealthy")

    @patch("micboard.models.Manufacturer.get_plugin_class")
    def test_api_health_plugin_exception(self, mock_get_manufacturer_plugin):
        _manufacturer1 = Manufacturer.objects.create(name="Shure", code="shure", is_active=True)

        mock_plugin_instance = MagicMock()
        mock_plugin_instance.check_health.side_effect = Exception("Plugin error")
        mock_get_manufacturer_plugin.return_value.return_value = mock_plugin_instance

        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "unhealthy")
        self.assertEqual(result["api_health"]["total_manufacturers"], 1)
        self.assertEqual(result["api_health"]["healthy_manufacturers"], 0)
        self.assertEqual(len(result["api_health"]["details"]), 1)
        self.assertEqual(result["api_health"]["details"][0]["status"], "error")
        self.assertIn("Plugin error", result["api_health"]["details"][0]["details"]["error"])

    @patch("micboard.models.Manufacturer.get_plugin_class")
    def test_api_health_cached_result(self, mock_get_manufacturer_plugin):
        _manufacturer1 = Manufacturer.objects.create(name="Shure", code="shure", is_active=True)

        mock_plugin_instance = MagicMock()
        mock_plugin_instance.check_health.return_value = {"status": "healthy"}
        mock_get_manufacturer_plugin.return_value.return_value = mock_plugin_instance

        # First call populates cache
        api_health(self.request)
        mock_get_manufacturer_plugin.return_value.return_value.check_health.assert_called_once()

        # Reset mock call count
        mock_get_manufacturer_plugin.return_value.return_value.check_health.reset_mock()

        # Second call should use cache
        result = api_health(self.request)

        self.assertIn("api_health", result)
        self.assertEqual(result["api_health"]["status"], "healthy")
        mock_get_manufacturer_plugin.return_value.return_value.check_health.assert_not_called()
