"""Tests for the unified Micboard settings service."""

from importlib import import_module
from unittest.mock import patch

from django.contrib.sites.models import Site
from django.test import TestCase, override_settings

from micboard.apps import MicboardConfig
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from micboard.services.settings.presentation_service import settings_presentation
from micboard.services.settings.registry import SettingsRegistry
from micboard.services.settings.settings_service import settings
from micboard.services.settings.visibility_service import settings_visibility
from tests.factories.base import UserFactory


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

    @override_settings(MICBOARD_CONFIG={"HOST_PRECEDENCE": "host-value"})
    def test_host_config_precedes_definition_default(self) -> None:
        """A registered definition must not suppress explicit host configuration."""
        SettingDefinition.objects.create(
            key="HOST_PRECEDENCE",
            label="Host precedence",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="definition-value",
        )

        self.assertEqual(SettingsRegistry.get("HOST_PRECEDENCE"), "definition-value")
        self.assertEqual(settings.get("HOST_PRECEDENCE"), "host-value")

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

    def test_ready_resolves_configuration_and_registers_model_lifecycle(self) -> None:
        """Initialize settings before connecting model lifecycle adapters."""
        app_config = MicboardConfig("micboard", import_module("micboard"))
        resolved_config = {
            "POLL_INTERVAL": 17,
            "CACHE_TIMEOUT": 31,
            "TRANSMITTER_INACTIVITY_SECONDS": 11,
        }
        startup_events: list[str] = []

        def resolve_config() -> dict[str, int]:
            startup_events.append("settings")
            return resolved_config

        def register_lifecycle() -> None:
            startup_events.append("lifecycle")

        with (
            patch.object(settings, "get_config_dict", side_effect=resolve_config) as get_config,
            patch(
                "micboard.model_lifecycle.register_model_lifecycle",
                side_effect=register_lifecycle,
            ) as register_lifecycle_mock,
            patch("django.core.checks.register"),
            patch.object(app_config, "_recommend_security_middleware"),
            patch.object(app_config, "_recommend_context_processors"),
            patch.object(app_config, "_register_background_tasks"),
        ):
            app_config.ready()

        get_config.assert_called_once_with()
        register_lifecycle_mock.assert_called_once_with()
        self.assertEqual(startup_events, ["settings", "lifecycle"])


class SettingsPresentationServiceTests(TestCase):
    """Settings presentation must stay scoped and query-efficient."""

    @override_settings(
        MICBOARD_MSP_ENABLED=False,
        MICBOARD_MULTI_SITE_MODE=True,
        SITE_ID=7,
    )
    def test_superuser_remains_scoped_to_current_site_in_multi_site_mode(self) -> None:
        """Platform permissions must not bypass non-MSP site isolation."""
        admin = UserFactory(is_superuser=True)

        scope = settings_visibility.for_user(user=admin)

        self.assertEqual(scope.organization_ids, frozenset())
        self.assertEqual(scope.site_ids, frozenset({7}))
        self.assertEqual(scope.manufacturer_ids, frozenset())
        self.assertFalse(settings_visibility.is_unrestricted(scope))

    @override_settings(
        MICBOARD_MSP_ENABLED=True,
        MICBOARD_MULTI_SITE_MODE=True,
        MICBOARD_ALLOW_CROSS_ORG_VIEW=True,
        SITE_ID=7,
    )
    def test_cross_org_superuser_is_intersected_with_current_site(self) -> None:
        """Cross-organization access must not become cross-site access."""
        current_site = Site.objects.create(pk=7, domain="settings-current.test", name="Current")
        foreign_site = Site.objects.create(pk=8, domain="settings-foreign.test", name="Foreign")
        current_organization = Organization.objects.create(
            name="Current Site Settings Organization",
            slug="current-site-settings-organization",
            site=current_site,
        )
        Organization.objects.create(
            name="Foreign Site Settings Organization",
            slug="foreign-site-settings-organization",
            site=foreign_site,
        )
        admin = UserFactory(is_superuser=True)

        scope = settings_visibility.for_user(user=admin)

        self.assertEqual(scope.organization_ids, frozenset({current_organization.pk}))
        self.assertEqual(scope.site_ids, frozenset({current_site.pk}))
        self.assertEqual(scope.manufacturer_ids, frozenset())
        self.assertFalse(settings_visibility.is_unrestricted(scope))

    @override_settings(
        MICBOARD_MSP_ENABLED=True,
        MICBOARD_MULTI_SITE_MODE=True,
        MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
        SITE_ID=7,
    )
    def test_memberships_are_intersected_with_current_site(self) -> None:
        """An active membership on another site must not expose its settings."""
        current_site = Site.objects.create(pk=7, domain="member-current.test", name="Current")
        foreign_site = Site.objects.create(pk=8, domain="member-foreign.test", name="Foreign")
        current_organization = Organization.objects.create(
            name="Current Member Settings Organization",
            slug="current-member-settings-organization",
            site=current_site,
        )
        foreign_organization = Organization.objects.create(
            name="Foreign Member Settings Organization",
            slug="foreign-member-settings-organization",
            site=foreign_site,
        )
        user = UserFactory(username="combined-mode-settings-user")
        OrganizationMembership.objects.create(user=user, organization=current_organization)
        OrganizationMembership.objects.create(user=user, organization=foreign_organization)

        scope = settings_visibility.for_user(user=user)

        self.assertEqual(scope.organization_ids, frozenset({current_organization.pk}))
        self.assertEqual(scope.site_ids, frozenset())
        self.assertEqual(scope.manufacturer_ids, frozenset())

    def test_unrestricted_diff_uses_a_fixed_query_budget(self) -> None:
        """Definitions must not trigger per-setting override queries."""
        admin = UserFactory(
            username="settings-query-admin",
            is_staff=True,
            is_superuser=True,
        )
        organization = Organization.objects.create(
            name="Settings Query Organization",
            slug="settings-query-organization",
        )
        manufacturer = Manufacturer.objects.create(
            name="Settings Query Manufacturer",
            code="settings-query-manufacturer",
        )
        organization_definition = SettingDefinition.objects.create(
            key="organization_label",
            label="Organization Label",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default",
        )
        manufacturer_definition = SettingDefinition.objects.create(
            key="manufacturer_label",
            label="Manufacturer Label",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default",
        )
        Setting.objects.create(
            definition=organization_definition,
            organization_id=organization.pk,
            value="organization-value",
        )
        Setting.objects.create(
            definition=manufacturer_definition,
            manufacturer_id=manufacturer.pk,
            value="manufacturer-value",
        )

        with self.assertNumQueries(4):
            context = settings_presentation.get_diff(user=admin)

        self.assertEqual(len(context["overrides"]), 2)

    @override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
    def test_restricted_superuser_without_membership_fails_closed(self) -> None:
        """Superuser status must not bypass an explicitly disabled tenant boundary."""
        admin = UserFactory(
            username="restricted-settings-admin",
            is_staff=True,
            is_superuser=True,
        )
        organization = Organization.objects.create(
            name="Foreign Settings Organization",
            slug="foreign-settings-organization",
        )
        definition = SettingDefinition.objects.create(
            key="foreign_setting",
            label="Foreign Setting",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default",
        )
        Setting.objects.create(
            definition=definition,
            organization_id=organization.pk,
            value="foreign-value",
        )

        context = settings_presentation.get_diff(user=admin)
        overview = settings_presentation.get_overview(user=admin)

        self.assertEqual(context["overrides"], [])
        self.assertFalse(overview["org_settings"].exists())

    @override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
    def test_visibility_ignores_revoked_and_inconsistent_memberships(self) -> None:
        """Only active, internally consistent memberships may expose settings."""
        user = UserFactory(username="settings-tenant-viewer")
        broad_org = Organization.objects.create(
            name="Broad Settings Organization",
            slug="broad-settings-organization",
        )
        scoped_org = Organization.objects.create(
            name="Scoped Settings Organization",
            slug="scoped-settings-organization",
        )
        scoped_campus = Campus.objects.create(
            organization=scoped_org,
            name="Scoped Settings Campus",
            slug="scoped-settings-campus",
        )
        inactive_org = Organization.objects.create(
            name="Inactive Settings Organization",
            slug="inactive-settings-organization",
            is_active=False,
        )
        inactive_campus_org = Organization.objects.create(
            name="Inactive Campus Settings Organization",
            slug="inactive-campus-settings-organization",
        )
        inactive_campus = Campus.objects.create(
            organization=inactive_campus_org,
            name="Inactive Settings Campus",
            slug="inactive-settings-campus",
            is_active=False,
        )
        inconsistent_org = Organization.objects.create(
            name="Inconsistent Settings Organization",
            slug="inconsistent-settings-organization",
        )
        foreign_org = Organization.objects.create(
            name="Foreign Settings Campus Organization",
            slug="foreign-settings-campus-organization",
        )
        foreign_campus = Campus.objects.create(
            organization=foreign_org,
            name="Foreign Settings Campus",
            slug="foreign-settings-campus",
        )

        OrganizationMembership.objects.create(user=user, organization=broad_org)
        OrganizationMembership.objects.create(
            user=user,
            organization=scoped_org,
            campus=scoped_campus,
        )
        OrganizationMembership.objects.create(user=user, organization=inactive_org)
        OrganizationMembership.objects.create(
            user=user,
            organization=inactive_campus_org,
            campus=inactive_campus,
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=inconsistent_org,
            campus=foreign_campus,
        )

        scope = settings_visibility.for_user(user=user)

        self.assertEqual(scope.organization_ids, frozenset({broad_org.pk}))
        self.assertFalse(
            settings_visibility.can_manage_scope(
                scope,
                organization_id=scoped_org.pk,
                site_id=None,
                manufacturer_id=None,
            )
        )
