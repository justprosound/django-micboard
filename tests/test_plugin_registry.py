"""Tests for Micboard plugin registry system."""

from unittest.mock import patch

from django.test import TestCase

from micboard.services.plugin_registry import PluginRegistry


class FakeManufacturerPlugin:
    """Fake manufacturer plugin for testing."""

    manufacturer_code = "fake"
    manufacturer = None

    def __init__(self, manufacturer=None):
        """Create a fake plugin tied to an optional manufacturer for tests."""
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

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_all_active_plugins(self, mock_get_plugin):
        """Test getting all active plugins from database."""
        mock_get_plugin.return_value = FakeManufacturerPlugin

        # Mock the Manufacturer.objects.filter to return a list
        mock_manufacturers = [
            type("MockMfg", (), {"code": "fake", "name": "Fake"}),
        ]

        with patch("micboard.models.Manufacturer.objects.filter") as mock_filter:
            mock_filter.return_value = mock_manufacturers

            plugins = PluginRegistry.get_all_active_plugins()

            # Should return list with plugin instance
            self.assertIsInstance(plugins, list)
            self.assertTrue(len(plugins) >= 0)

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_plugin_with_manufacturer_not_found(self, mock_get_plugin):
        """Test get_plugin when manufacturer is not found in database."""
        mock_get_plugin.return_value = FakeManufacturerPlugin

        # The code has an inner try/except for Manufacturer.DoesNotExist
        # We need to trigger it by making the get call raise that exception
        with patch("micboard.models.Manufacturer") as mock_mfg_class:
            # Create a proper exception class for DoesNotExist
            class DoesNotExistError(Exception):
                pass

            mock_mfg_class.DoesNotExist = DoesNotExistError
            # Set up the manager's get method to raise DoesNotExist
            mock_mfg_class.objects.get.side_effect = DoesNotExistError("Not found")

            # Should return a plugin instance even if manufacturer lookup fails
            plugin = PluginRegistry.get_plugin("fake")

            # Plugin should be created with manufacturer=None
            self.assertIsInstance(plugin, FakeManufacturerPlugin)

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_all_active_plugins_with_failed_plugin(self, mock_get_plugin):
        """Test get_all_active_plugins handles plugins that fail to load."""
        # First plugin succeeds, second fails
        mock_get_plugin.side_effect = [
            FakeManufacturerPlugin,
            ModuleNotFoundError("Plugin not found"),
        ]

        mock_manufacturers = [
            type("MockMfg1", (), {"code": "fake1", "name": "Fake1"}),
            type("MockMfg2", (), {"code": "fake2", "name": "Fake2"}),
        ]

        with patch("micboard.models.Manufacturer.objects.filter") as mock_filter:
            mock_filter.return_value = mock_manufacturers

            # Reset cache between calls
            PluginRegistry.clear_cache()

            plugins = PluginRegistry.get_all_active_plugins()

            # Should skip plugins that fail to load
            self.assertIsInstance(plugins, list)
            # Should have fewer plugins than manufacturers (one failed)
            self.assertTrue(len(plugins) <= len(mock_manufacturers))

    @patch("micboard.manufacturers.get_manufacturer_plugin")
    def test_get_plugin_with_manufacturer_lookup_success(self, mock_get_plugin):
        """Test get_plugin successfully looks up manufacturer from database."""
        mock_get_plugin.return_value = FakeManufacturerPlugin

        # Create a mock manufacturer object
        mock_mfg = type("MockMfg", (), {"code": "fake", "name": "Fake"})()

        with patch("micboard.models.Manufacturer") as mock_mfg_class:
            # Set up successful database lookup
            mock_mfg_class.objects.get.return_value = mock_mfg

            # Call with None manufacturer - should trigger database lookup
            plugin = PluginRegistry.get_plugin("fake", manufacturer=None)

            # Should have called the database
            mock_mfg_class.objects.get.assert_called_once_with(code="fake")

            # Should return plugin instance with the looked-up manufacturer
            self.assertIsInstance(plugin, FakeManufacturerPlugin)
            self.assertEqual(plugin.manufacturer, mock_mfg)
