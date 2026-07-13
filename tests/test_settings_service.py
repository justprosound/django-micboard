"""Tests for the unified Micboard settings service."""

from importlib import import_module
from unittest.mock import patch

from django.test import TestCase, override_settings

from micboard.apps import MicboardConfig
from micboard.services.settings import settings


class SettingsServiceTests(TestCase):
    """Test the public settings service API."""

    def test_default_values(self) -> None:
        """Return documented defaults when the host does not override them."""
        self.assertFalse(settings.msp_enabled)
        self.assertFalse(settings.multi_site_mode)
        self.assertEqual(settings.site_isolation, "none")
        self.assertTrue(settings.allow_cross_org_view)

    @override_settings(MICBOARD_MSP_ENABLED=True)
    def test_msp_enabled_flag(self) -> None:
        """Resolve the MSP feature flag from Django settings."""
        self.assertTrue(settings.msp_enabled)

    @override_settings(MICBOARD_MULTI_SITE_MODE=True)
    def test_multi_site_mode_flag(self) -> None:
        """Resolve the multi-site feature flag from Django settings."""
        self.assertTrue(settings.multi_site_mode)

    @override_settings(MICBOARD_SITE_ISOLATION="organization")
    def test_site_isolation_setting(self) -> None:
        """Resolve the configured site-isolation mode."""
        self.assertEqual(settings.site_isolation, "organization")

    @override_settings(MICBOARD_CONFIG={"SHURE_API_TIMEOUT": 30})
    def test_get_from_config_dict(self) -> None:
        """Resolve generic keys from the host's MICBOARD_CONFIG dictionary."""
        self.assertEqual(settings.get("SHURE_API_TIMEOUT"), 30)

    @override_settings(MICBOARD_CONFIG={"CUSTOM_KEY": "custom_value"})
    def test_get_with_default(self) -> None:
        """Return the explicit default when no source defines a key."""
        self.assertEqual(settings.get("MISSING_KEY", default="fallback"), "fallback")

    @override_settings(MICBOARD_CONFIG={"KEY1": "value1", "KEY2": "value2"})
    def test_get_config_dict(self) -> None:
        """Merge AppConfig defaults with the host configuration dictionary."""
        config = settings.get_config_dict()

        self.assertEqual(config["POLL_INTERVAL"], 5)
        self.assertEqual(config["KEY1"], "value1")
        self.assertEqual(config["KEY2"], "value2")

    @override_settings(MICBOARD_ADMIN_ORG_SELECTOR=False)
    def test_admin_org_selector(self) -> None:
        """Resolve the admin organization-selector flag."""
        self.assertFalse(settings.admin_org_selector)

    @override_settings(MICBOARD_GLOBAL_DEVICE_LIMIT=1000)
    def test_global_device_limit(self) -> None:
        """Resolve the global device limit."""
        self.assertEqual(settings.global_device_limit, 1000)

    @override_settings(MICBOARD_DEVICE_LIMIT_WARNING_THRESHOLD=0.75)
    def test_device_limit_warning_threshold(self) -> None:
        """Resolve the device-limit warning threshold."""
        self.assertEqual(settings.device_limit_warning_threshold, 0.75)

    @override_settings(MICBOARD_ACTIVITY_LOG_RETENTION_DAYS=60)
    def test_activity_log_retention_days(self) -> None:
        """Resolve the activity-log retention period."""
        self.assertEqual(settings.activity_log_retention_days, 60)

    @override_settings(MICBOARD_SERVICE_SYNC_LOG_RETENTION_DAYS=15)
    def test_service_sync_log_retention_days(self) -> None:
        """Resolve the service-sync-log retention period."""
        self.assertEqual(settings.service_sync_log_retention_days, 15)

    @override_settings(MICBOARD_API_HEALTH_LOG_RETENTION_DAYS=3)
    def test_api_health_log_retention_days(self) -> None:
        """Resolve the API-health-log retention period."""
        self.assertEqual(settings.api_health_log_retention_days, 3)

    @override_settings(MICBOARD_AUDIT_ARCHIVE_PATH="/var/audit")
    def test_audit_archive_path(self) -> None:
        """Resolve the audit archive path."""
        self.assertEqual(settings.audit_archive_path, "/var/audit")

    @override_settings(TESTING=True)
    def test_testing_flag(self) -> None:
        """Expose the host's testing flag."""
        self.assertTrue(settings.testing)

    @override_settings(MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
    def test_allow_cross_org_view(self) -> None:
        """Resolve the cross-organization visibility flag."""
        self.assertFalse(settings.allow_cross_org_view)

    @override_settings(MICBOARD_ALLOW_ORG_SWITCHING=False)
    def test_allow_org_switching(self) -> None:
        """Resolve the organization-switching flag."""
        self.assertFalse(settings.allow_org_switching)

    @override_settings(MICBOARD_SUBDOMAIN_ROUTING=True)
    def test_subdomain_routing(self) -> None:
        """Resolve the subdomain-routing flag."""
        self.assertTrue(settings.subdomain_routing)

    @override_settings(MICBOARD_ROOT_DOMAIN="micboard.example.com")
    def test_root_domain(self) -> None:
        """Resolve the root domain."""
        self.assertEqual(settings.root_domain, "micboard.example.com")


class MicboardAppConfigTests(TestCase):
    """Test settings resolution during Django app startup."""

    def test_ready_resolves_configuration_through_settings_service(self) -> None:
        """Keep direct MICBOARD_CONFIG reads behind SettingsService."""
        app_config = MicboardConfig("micboard", import_module("micboard"))
        resolved_config = {
            "POLL_INTERVAL": 17,
            "CACHE_TIMEOUT": 31,
            "TRANSMITTER_INACTIVITY_SECONDS": 11,
        }

        with (
            patch.object(MicboardConfig, "_resolved_config", MicboardConfig._resolved_config),
            patch.object(settings, "get_config_dict", return_value=resolved_config) as get_config,
            patch("django.core.checks.register"),
            patch.object(app_config, "_register_security_middleware"),
            patch.object(app_config, "_register_context_processors"),
            patch.object(app_config, "_register_background_tasks"),
        ):
            app_config.ready()
            self.assertEqual(MicboardConfig.get_config(), resolved_config)

        get_config.assert_called_once_with()
