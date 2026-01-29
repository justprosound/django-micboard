"""Tests for settings management system."""

from django.contrib.sites.models import Site
from django.db import IntegrityError
from django.test import TestCase

from micboard.models.discovery import Manufacturer
from micboard.models.settings import Setting, SettingDefinition
from micboard.multitenancy.models import Organization
from micboard.services.manufacturer_config_registry import ManufacturerConfigRegistry
from micboard.services.settings_registry import SettingsRegistry


class SettingDefinitionTests(TestCase):
    """Test SettingDefinition model."""

    def test_unique_key(self):
        """Test that setting keys are unique."""
        SettingDefinition.objects.create(
            key="test_setting",
            label="Test",
            setting_type=SettingDefinition.TYPE_STRING,
        )

        with self.assertRaises(IntegrityError):
            SettingDefinition.objects.create(
                key="test_setting",
                label="Test 2",
                setting_type=SettingDefinition.TYPE_STRING,
            )

    def test_parse_string(self):
        """Test parsing string values."""
        defn = SettingDefinition.objects.create(
            key="string_test",
            label="String Test",
            setting_type=SettingDefinition.TYPE_STRING,
        )
        parsed = defn.parse_value("hello world")
        self.assertEqual(parsed, "hello world")
        self.assertIsInstance(parsed, str)

    def test_parse_integer(self):
        """Test parsing integer values."""
        defn = SettingDefinition.objects.create(
            key="int_test",
            label="Integer Test",
            setting_type=SettingDefinition.TYPE_INTEGER,
        )
        parsed = defn.parse_value("42")
        self.assertEqual(parsed, 42)
        self.assertIsInstance(parsed, int)

    def test_parse_boolean_true(self):
        """Test parsing boolean true values."""
        defn = SettingDefinition.objects.create(
            key="bool_test",
            label="Boolean Test",
            setting_type=SettingDefinition.TYPE_BOOLEAN,
        )

        for true_value in ["true", "True", "TRUE", "1", "yes", "Yes"]:
            parsed = defn.parse_value(true_value)
            self.assertTrue(parsed, f"Failed for {true_value}")

    def test_parse_boolean_false(self):
        """Test parsing boolean false values."""
        defn = SettingDefinition.objects.create(
            key="bool_test",
            label="Boolean Test",
            setting_type=SettingDefinition.TYPE_BOOLEAN,
        )

        for false_value in ["false", "False", "FALSE", "0", "no", "No"]:
            parsed = defn.parse_value(false_value)
            self.assertFalse(parsed, f"Failed for {false_value}")

    def test_parse_json(self):
        """Test parsing JSON values."""
        defn = SettingDefinition.objects.create(
            key="json_test",
            label="JSON Test",
            setting_type=SettingDefinition.TYPE_JSON,
        )
        parsed = defn.parse_value('{"key": "value", "number": 42}')
        self.assertEqual(parsed["key"], "value")
        self.assertEqual(parsed["number"], 42)

    def test_serialize_integer(self):
        """Test serializing integer values."""
        defn = SettingDefinition.objects.create(
            key="int_test",
            label="Integer Test",
            setting_type=SettingDefinition.TYPE_INTEGER,
        )
        serialized = defn.serialize_value(42)
        self.assertEqual(serialized, "42")
        self.assertIsInstance(serialized, str)

    def test_serialize_boolean(self):
        """Test serializing boolean values."""
        defn = SettingDefinition.objects.create(
            key="bool_test",
            label="Boolean Test",
            setting_type=SettingDefinition.TYPE_BOOLEAN,
        )
        self.assertEqual(defn.serialize_value(True), "true")
        self.assertEqual(defn.serialize_value(False), "false")


class SettingTests(TestCase):
    """Test Setting model."""

    def setUp(self):
        self.defn = SettingDefinition.objects.create(
            key="test_setting",
            label="Test Setting",
            setting_type=SettingDefinition.TYPE_INTEGER,
            default_value="100",
        )
        self.org = Organization.objects.create(name="Test Org")
        self.site = Site.objects.create(name="Test Site", organization=self.org)

    def test_unique_together_constraint(self):
        """Test that unique_together prevents duplicate scopes."""
        Setting.objects.create(
            definition=self.defn,
            organization=self.org,
            value="50",
        )

        with self.assertRaises(IntegrityError):
            Setting.objects.create(
                definition=self.defn,
                organization=self.org,
                value="75",
            )

    def test_multiple_scopes_allowed(self):
        """Test that same setting can exist at different scopes."""
        Setting.objects.create(
            definition=self.defn,
            organization=self.org,
            value="50",
        )

        Setting.objects.create(
            definition=self.defn,
            site=self.site,
            value="75",
        )

        # Should not raise
        self.assertEqual(Setting.objects.count(), 2)

    def test_get_parsed_value(self):
        """Test get_parsed_value method."""
        setting = Setting.objects.create(
            definition=self.defn,
            organization=self.org,
            value="42",
        )

        parsed = setting.get_parsed_value()
        self.assertEqual(parsed, 42)
        self.assertIsInstance(parsed, int)

    def test_set_value(self):
        """Test set_value method."""
        setting = Setting.objects.create(
            definition=self.defn,
            organization=self.org,
            value="0",
        )

        setting.set_value(123)
        setting.refresh_from_db()

        self.assertEqual(setting.value, "123")
        self.assertEqual(setting.get_parsed_value(), 123)


class SettingsRegistryTests(TestCase):
    """Test SettingsRegistry service."""

    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.site = Site.objects.create(name="Test Site", organization=self.org)
        self.mfg = Manufacturer.objects.create(name="Test Mfg", code="test")

    def test_get_global_setting(self):
        """Test getting a global setting."""
        SettingDefinition.objects.create(
            key="global_test",
            label="Global Test",
            setting_type=SettingDefinition.TYPE_STRING,
            scope=SettingDefinition.SCOPE_GLOBAL,
            default_value="default",
        )

        value = SettingsRegistry.get("global_test")
        self.assertEqual(value, "default")

    def test_get_with_database_value(self):
        """Test getting a setting that exists in database."""
        defn = SettingDefinition.objects.create(
            key="db_test",
            label="DB Test",
            setting_type=SettingDefinition.TYPE_INTEGER,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
            default_value="100",
        )

        Setting.objects.create(
            definition=defn,
            organization=self.org,
            value="200",
        )

        value = SettingsRegistry.get("db_test", organization=self.org)
        self.assertEqual(value, 200)

    def test_scope_fallback_chain(self):
        """Test fallback through scope hierarchy."""
        defn = SettingDefinition.objects.create(
            key="fallback_test",
            label="Fallback Test",
            setting_type=SettingDefinition.TYPE_INTEGER,
            scope=SettingDefinition.SCOPE_MANUFACTURER,
            default_value="10",
        )

        # Create org-level override
        Setting.objects.create(
            definition=defn,
            organization=self.org,
            value="20",
        )

        # Get with organization and site - should fall back to org
        value = SettingsRegistry.get(
            "fallback_test",
            organization=self.org,
            site=self.site,
            required=False,
        )
        self.assertEqual(value, 20)

    def test_required_setting_not_found(self):
        """Test that required setting raises error if not found."""
        SettingDefinition.objects.create(
            key="required_test",
            label="Required Test",
            setting_type=SettingDefinition.TYPE_STRING,
            required=True,
        )

        with self.assertRaises(ValueError):
            SettingsRegistry.get("required_test", required=True)

    def test_set_and_get(self):
        """Test setting a value and retrieving it."""
        SettingDefinition.objects.create(
            key="set_test",
            label="Set Test",
            setting_type=SettingDefinition.TYPE_STRING,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
        )

        SettingsRegistry.set("set_test", "new_value", organization=self.org)

        value = SettingsRegistry.get("set_test", organization=self.org)
        self.assertEqual(value, "new_value")

    def test_cache_invalidation(self):
        """Test that cache invalidation works."""
        defn = SettingDefinition.objects.create(
            key="cache_test",
            label="Cache Test",
            setting_type=SettingDefinition.TYPE_INTEGER,
            default_value="100",
        )

        # Get value (will be cached)
        value1 = SettingsRegistry.get("cache_test")
        self.assertEqual(value1, 100)

        # Update directly in DB
        Setting.objects.create(
            definition=defn,
            organization=self.org,
            value="200",
        )

        # Without invalidation, still returns cached value
        value2 = SettingsRegistry.get("cache_test")
        self.assertEqual(value2, 100)

        # Invalidate and get again
        SettingsRegistry.invalidate_cache("cache_test")
        value3 = SettingsRegistry.get("cache_test")
        # Note: This should now return 100 (default) since no org specified
        self.assertEqual(value3, 100)

    def test_get_all_for_scope(self):
        """Test bulk retrieval for a scope."""
        defn1 = SettingDefinition.objects.create(
            key="bulk_test_1",
            label="Bulk Test 1",
            setting_type=SettingDefinition.TYPE_STRING,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
        )
        defn2 = SettingDefinition.objects.create(
            key="bulk_test_2",
            label="Bulk Test 2",
            setting_type=SettingDefinition.TYPE_INTEGER,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
        )

        Setting.objects.create(definition=defn1, organization=self.org, value="value1")
        Setting.objects.create(definition=defn2, organization=self.org, value="42")

        all_settings = SettingsRegistry.get_all_for_scope(organization=self.org)

        self.assertEqual(all_settings["bulk_test_1"], "value1")
        self.assertEqual(all_settings["bulk_test_2"], 42)


class ManufacturerConfigRegistryTests(TestCase):
    """Test ManufacturerConfigRegistry service."""

    def setUp(self):
        self.mfg = Manufacturer.objects.create(name="Shure", code="shure")

    def test_get_shure_defaults(self):
        """Test getting Shure manufacturer defaults."""
        config = ManufacturerConfigRegistry.get("shure", manufacturer=self.mfg)

        self.assertEqual(config.battery_good_level, 90)
        self.assertEqual(config.battery_low_level, 20)
        self.assertEqual(config.battery_critical_level, 0)

    def test_override_with_database_setting(self):
        """Test that database settings override defaults."""
        # Create override
        defn = SettingDefinition.objects.create(
            key="battery_good_level",
            label="Battery Good Level",
            setting_type=SettingDefinition.TYPE_INTEGER,
            scope=SettingDefinition.SCOPE_MANUFACTURER,
            default_value="90",
        )

        Setting.objects.create(
            definition=defn,
            manufacturer=self.mfg,
            value="95",
        )

        config = ManufacturerConfigRegistry.get("shure", manufacturer=self.mfg)

        # Should use override, not default
        self.assertEqual(config.battery_good_level, 95)

    def test_missing_manufacturer(self):
        """Test behavior for unknown manufacturer."""
        config = ManufacturerConfigRegistry.get("unknown", manufacturer=self.mfg)

        # Should return defaults (empty config)
        self.assertIsNotNone(config)


class SettingIntegrationTests(TestCase):
    """Integration tests for settings workflow."""

    def test_full_workflow(self):
        """Test complete workflow: define, configure, retrieve."""
        # 1. Create definition
        defn = SettingDefinition.objects.create(
            key="workflow_test",
            label="Workflow Test",
            description="Testing the full workflow",
            setting_type=SettingDefinition.TYPE_INTEGER,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
            default_value="100",
        )

        org = Organization.objects.create(name="Test Org")

        # 2. Configure value via registry
        SettingsRegistry.set("workflow_test", 250, organization=org)

        # 3. Retrieve and verify
        value = SettingsRegistry.get("workflow_test", organization=org)
        self.assertEqual(value, 250)

        # 4. Verify database contains it
        setting = Setting.objects.get(definition=defn, organization=org)
        self.assertEqual(setting.value, "250")

    def test_multi_tenant_isolation(self):
        """Test that settings are properly isolated by tenant."""
        SettingDefinition.objects.create(
            key="tenant_test",
            label="Tenant Test",
            setting_type=SettingDefinition.TYPE_STRING,
            scope=SettingDefinition.SCOPE_ORGANIZATION,
        )

        org1 = Organization.objects.create(name="Org 1")
        org2 = Organization.objects.create(name="Org 2")

        # Different values per org
        SettingsRegistry.set("tenant_test", "org1_value", organization=org1)
        SettingsRegistry.set("tenant_test", "org2_value", organization=org2)

        # Verify isolation
        value1 = SettingsRegistry.get("tenant_test", organization=org1)
        value2 = SettingsRegistry.get("tenant_test", organization=org2)

        self.assertEqual(value1, "org1_value")
        self.assertEqual(value2, "org2_value")
        self.assertNotEqual(value1, value2)
