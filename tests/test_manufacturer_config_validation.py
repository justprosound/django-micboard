"""How a manufacturer configuration is validated.

Validation answers one operator question: would a poll using this configuration work? That
needs a plugin built for the configured code, a client it can reach, and the fields the
integration requires.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.services.manufacturer.config import (
    REQUIRED_FIELDS_MAP,
    apply_manufacturer_config,
    validate_manufacturer_config,
)
from tests.factories.discovery import ManufacturerFactory


class FakePlugin:
    manufacturer_code = "test_mfr"

    def get_client(self) -> MagicMock:
        return MagicMock()


class FakePluginNoClient:
    manufacturer_code = "test_mfr"

    def get_client(self) -> None:
        return None


class FakePluginBrokenClient:
    manufacturer_code = "test_mfr"

    def get_client(self) -> None:
        raise RuntimeError("Connection refused")


class ValidateManufacturerConfigTests(TestCase):
    """Tests for validate_manufacturer_config()."""

    def _make_config(
        self, code: str = "test_mfr", config: dict | None = None
    ) -> ManufacturerConfiguration:
        ManufacturerFactory(code=code)
        return ManufacturerConfiguration(
            code=code,
            name="Test Manufacturer",
            config=config or {},
        )

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_valid_config(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePlugin()
        cfg = self._make_config(
            code="shure",
            config={
                "SHURE_API_BASE_URL": "https://api.example.com",
                "SHURE_API_SHARED_KEY": "sekret",
            },
        )

        result = validate_manufacturer_config(config=cfg)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])

    def test_configuration_for_an_unregistered_manufacturer_is_invalid(self):
        """Nothing polls a configuration whose code has no manufacturer row behind it."""
        cfg = ManufacturerConfiguration(code="orphan", name="Orphan", config={})

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertIn("No manufacturer registered for code: orphan", errors)

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_plugin_not_found(self, mock_build_plugin):
        mock_build_plugin.side_effect = ModuleNotFoundError("no integration for unknown")
        cfg = self._make_config(code="unknown")

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertIn("Plugin not found or not enabled: unknown", errors)

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_an_unbuildable_plugin_reports_one_failure_shape(self, mock_build_plugin):
        """A missing module and an unusable plugin class are the same operator error."""
        mock_build_plugin.side_effect = ImportError("No module named 'x'")
        cfg = self._make_config()

        result = validate_manufacturer_config(config=cfg)

        self.assertFalse(result["is_valid"])
        self.assertEqual(result["errors"], ["Plugin not found or not enabled: test_mfr"])

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_plugin_init_other_error_caught(self, mock_build_plugin):
        mock_build_plugin.side_effect = RuntimeError("Boom")
        cfg = self._make_config()

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("Plugin initialization failed" in e for e in errors))

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_client_returns_none(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePluginNoClient()
        cfg = self._make_config()

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertIn("Plugin client initialization failed for test_mfr", errors)

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_client_raises_exception(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePluginBrokenClient()
        cfg = self._make_config()

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("Plugin health check failed" in e for e in errors))

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_missing_required_fields(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePlugin()
        cfg = self._make_config(code="shure", config={})

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        for field in REQUIRED_FIELDS_MAP["shure"]:
            self.assertTrue(any(f"Missing required configuration: {field}" in e for e in errors))

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_unknown_code_skips_field_validation(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePlugin()
        cfg = self._make_config(code="unknown_vendor")

        result = validate_manufacturer_config(config=cfg)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_does_not_mutate_config(self, mock_build_plugin):
        mock_build_plugin.return_value = FakePlugin()
        cfg = self._make_config(
            code="shure",
            config={
                "SHURE_API_BASE_URL": "https://api.example.com",
                "SHURE_API_SHARED_KEY": "sekret",
            },
        )
        original_valid = cfg.is_valid
        original_errors = cfg.validation_errors
        original_validated = cfg.last_validated

        validate_manufacturer_config(config=cfg)

        self.assertEqual(cfg.is_valid, original_valid)
        self.assertEqual(cfg.validation_errors, original_errors)
        self.assertEqual(cfg.last_validated, original_validated)

    @patch("micboard.services.manufacturer.config.build_manufacturer_plugin")
    def test_multiple_errors(self, mock_build_plugin):
        mock_build_plugin.side_effect = ModuleNotFoundError("no integration for shure")
        cfg = self._make_config(code="shure", config={})

        result = validate_manufacturer_config(config=cfg)
        errors: list[str] = result["errors"]  # type: ignore[assignment]

        self.assertFalse(result["is_valid"])
        self.assertGreaterEqual(len(errors), 2)


class ApplyManufacturerConfigTests(TestCase):
    """Tests for apply_manufacturer_config()."""

    def test_valid_config_returns_true(self):
        cfg = ManufacturerConfiguration(code="test", name="Test", is_valid=True, config={})

        result = apply_manufacturer_config(config=cfg)

        self.assertTrue(result)

    def test_invalid_config_returns_false(self):
        cfg = ManufacturerConfiguration(code="test", name="Test", is_valid=False, config={})

        result = apply_manufacturer_config(config=cfg)

        self.assertFalse(result)

    @patch("micboard.services.manufacturer.config.logger")
    def test_invalid_config_logs_warning(self, mock_logger):
        cfg = ManufacturerConfiguration(code="test", name="Test", is_valid=False, config={})

        apply_manufacturer_config(config=cfg)

        mock_logger.warning.assert_called_once()

    @patch("micboard.services.manufacturer.config.logger")
    def test_exception_in_check_logs_error(self, mock_logger):
        mock_logger.info.side_effect = RuntimeError("Log failure")
        cfg = ManufacturerConfiguration(code="test", name="Test", is_valid=True, config={})

        result = apply_manufacturer_config(config=cfg)

        self.assertFalse(result)
        mock_logger.exception.assert_called_once()
        self.assertNotIn("Log failure", str(mock_logger.exception.call_args))
