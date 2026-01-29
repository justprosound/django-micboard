"""Tests for the Micboard configuration and settings system."""

from django.test import TestCase, override_settings

from micboard.conf import config


class MicboardConfTests(TestCase):
    """Test the centralized Micboard configuration proxy."""

    def test_default_values(self):
        """Test default configuration values."""
        # These should return defaults without any settings
        self.assertFalse(config.msp_enabled)
        self.assertFalse(config.multi_site_mode)
        self.assertEqual(config.site_isolation, "none")
        self.assertTrue(config.allow_cross_org_view)

    @override_settings(MICBOARD_MSP_ENABLED=True)
    def test_msp_enabled_flag(self):
        """Test MSP enabled flag."""
        self.assertTrue(config.msp_enabled)

    @override_settings(MICBOARD_MULTI_SITE_MODE=True)
    def test_multi_site_mode_flag(self):
        """Test multi-site mode flag."""
        self.assertTrue(config.multi_site_mode)

    @override_settings(MICBOARD_SITE_ISOLATION="organization")
    def test_site_isolation_setting(self):
        """Test site isolation setting."""
        self.assertEqual(config.site_isolation, "organization")

    @override_settings(MICBOARD_CONFIG={"SHURE_API_TIMEOUT": 30})
    def test_get_from_config_dict(self):
        """Test get method for MICBOARD_CONFIG dict."""
        value = config.get("SHURE_API_TIMEOUT")
        self.assertEqual(value, 30)

    @override_settings(MICBOARD_CONFIG={"CUSTOM_KEY": "custom_value"})
    def test_get_with_default(self):
        """Test get method with default value."""
        value = config.get("MISSING_KEY", default="fallback")
        self.assertEqual(value, "fallback")

    def test_get_config_dict(self):
        """Test retrieving entire config dict."""
        with override_settings(MICBOARD_CONFIG={"KEY1": "value1", "KEY2": "value2"}):
            cfg_dict = config.get_config_dict()
            self.assertEqual(cfg_dict["KEY1"], "value1")
            self.assertEqual(cfg_dict["KEY2"], "value2")

    @override_settings(MICBOARD_ADMIN_ORG_SELECTOR=False)
    def test_admin_org_selector(self):
        """Test admin org selector flag."""
        self.assertFalse(config.admin_org_selector)

    @override_settings(MICBOARD_GLOBAL_DEVICE_LIMIT=1000)
    def test_global_device_limit(self):
        """Test global device limit."""
        self.assertEqual(config.global_device_limit, 1000)

    @override_settings(MICBOARD_DEVICE_LIMIT_WARNING_THRESHOLD=0.75)
    def test_device_limit_warning_threshold(self):
        """Test device limit warning threshold."""
        self.assertEqual(config.device_limit_warning_threshold, 0.75)

    @override_settings(MICBOARD_ACTIVITY_LOG_RETENTION_DAYS=60)
    def test_activity_log_retention_days(self):
        """Test activity log retention setting."""
        self.assertEqual(config.activity_log_retention_days, 60)

    @override_settings(MICBOARD_SERVICE_SYNC_LOG_RETENTION_DAYS=15)
    def test_service_sync_log_retention_days(self):
        """Test service sync log retention setting."""
        self.assertEqual(config.service_sync_log_retention_days, 15)

    @override_settings(MICBOARD_API_HEALTH_LOG_RETENTION_DAYS=3)
    def test_api_health_log_retention_days(self):
        """Test API health log retention setting."""
        self.assertEqual(config.api_health_log_retention_days, 3)

    @override_settings(MICBOARD_AUDIT_ARCHIVE_PATH="/var/audit")
    def test_audit_archive_path(self):
        """Test audit archive path."""
        self.assertEqual(config.audit_archive_path, "/var/audit")

    @override_settings(TESTING=True)
    def test_testing_flag(self):
        """Test testing flag."""
        self.assertTrue(config.testing)

    @override_settings(MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
    def test_allow_cross_org_view(self):
        """Test allow cross org view flag."""
        self.assertFalse(config.allow_cross_org_view)

    @override_settings(MICBOARD_ALLOW_ORG_SWITCHING=False)
    def test_allow_org_switching(self):
        """Test allow org switching flag."""
        self.assertFalse(config.allow_org_switching)

    @override_settings(MICBOARD_SUBDOMAIN_ROUTING=True)
    def test_subdomain_routing(self):
        """Test subdomain routing flag."""
        self.assertTrue(config.subdomain_routing)

    @override_settings(MICBOARD_ROOT_DOMAIN="micboard.example.com")
    def test_root_domain(self):
        """Test root domain setting."""
        self.assertEqual(config.root_domain, "micboard.example.com")
