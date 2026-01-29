"""Tests for Micboard plugin registry system."""

from unittest.mock import patch

from django.test import TestCase

from micboard.services.plugin_registry import PluginRegistry


class FakeManufacturerPlugin:
    """Fake manufacturer plugin for testing."""

    manufacturer_code = "fake"
    manufacturer = None

    def __init__(self, manufacturer=None):
        self.manufacturer = manufacturer

    def get_devices(self):
        """Fake get_devices method."""
        return []

    def poll_device(self, device_id):
        """Fake poll_device method."""
        return {}


class PluginRegistryTests(TestCase):
    """Test the Plugin Registry."""

    def setUp(self):
        """Set up test dependencies."""
        # Clear plugin cache before each test
        PluginRegistry.clear_cache()

    def tearDown(self):
        """Clean up after tests."""
        PluginRegistry.clear_cache()

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_plugin_class_caches_result(self, mock_get_plugin):
        """Test that plugin class is cached after first load."""
        mock_get_plugin.return_value = FakeManufacturerPlugin

        # First call
        plugin1 = PluginRegistry.get_plugin_class("fake")
        self.assertEqual(plugin1, FakeManufacturerPlugin)

        # Second call should use cache (not call mock again)
        plugin2 = PluginRegistry.get_plugin_class("fake")
        self.assertEqual(plugin2, FakeManufacturerPlugin)

        # Mock should only be called once
        self.assertEqual(mock_get_plugin.call_count, 1)

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_plugin_not_found_returns_none(self, mock_get_plugin):
        """Test that missing plugin returns None."""
        mock_get_plugin.side_effect = ModuleNotFoundError("No plugin")

        plugin = PluginRegistry.get_plugin("nonexistent")

        self.assertIsNone(plugin)

    def test_clear_cache(self):
        """Test cache clearing."""
        with patch("micboard.manufacturers.get_manufacturer_plugin") as mock_get:
            mock_get.return_value = FakeManufacturerPlugin

            # Fill cache
            PluginRegistry.get_plugin_class("fake")

            # Clear cache
            PluginRegistry.clear_cache()

            # Reset mock call count
            mock_get.reset_mock()

            # Load again - should call mock again since cache was cleared
            PluginRegistry.get_plugin_class("fake")
            self.assertEqual(mock_get.call_count, 1)

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_plugin_loading_error_handling(self, mock_get_plugin):
        """Test error handling when plugin loading fails."""
        mock_get_plugin.side_effect = ImportError("Import failed")

        with self.assertRaises(ImportError):
            PluginRegistry.get_plugin_class("fake")
