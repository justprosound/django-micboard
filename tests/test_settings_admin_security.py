"""Authorization and secret-redaction coverage for settings administration."""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.sites.models import Site
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from micboard.forms.settings import BulkSettingConfigForm, ManufacturerSettingsForm
from micboard.forms.settings_admin import SettingDefinitionForm
from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.shared.settings_registry import SettingsRegistry
from micboard.views.settings import BulkSettingConfigView, ManufacturerSettingsView
from tests.admin.helpers import create_tenant_inventory
from tests.factories.base import UserFactory


class SettingsAdminSecretRedactionTests(TestCase):
    """Unknown definitions must remain secret in every standard admin surface."""

    def setUp(self) -> None:
        self.admin = UserFactory(is_staff=True, is_superuser=True)
        self.definition = SettingDefinition.objects.create(
            key="OAUTH_CREDENTIAL",
            label="OAuth credential",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default-secret-material",
        )
        self.setting = Setting.objects.create(
            definition=self.definition,
            value="stored-secret-material",
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_standard_setting_admin_never_renders_unknown_value(self) -> None:
        """Changelist and detail views must mask raw and parsed values."""
        responses = (
            self.client.get(reverse("admin:micboard_setting_changelist")),
            self.client.get(reverse("admin:micboard_setting_change", args=[self.setting.pk])),
        )

        for response in responses:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "••••••")
                self.assertNotContains(response, "stored-secret-material")

        self.assertContains(responses[1], 'type="password"')

    def test_standard_definition_admin_never_renders_unknown_default(self) -> None:
        """Definition detail must mask and avoid pre-filling a sensitive default."""
        response = self.client.get(
            reverse("admin:micboard_settingdefinition_change", args=[self.definition.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "••••••")
        self.assertContains(response, 'type="password"')
        self.assertNotContains(response, "default-secret-material")

    def test_setting_string_representation_contains_no_value(self) -> None:
        """Logs and relationship widgets must not receive raw setting text."""
        self.assertNotIn("stored-secret-material", str(self.setting))


class SettingsAdminCacheInvalidationTests(TestCase):
    """Admin mutations must make cached settings changes visible immediately."""

    def setUp(self) -> None:
        self.admin = UserFactory(is_staff=True, is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin)

    def test_definition_edit_invalidates_cached_default(self) -> None:
        """Changing definition metadata must evict the process-local definition cache."""
        definition = SettingDefinition.objects.create(
            key="poll_interval",
            label="Poll interval",
            setting_type=SettingDefinition.TYPE_INTEGER,
            default_value="5",
        )
        self.assertEqual(SettingsRegistry.get("poll_interval"), 5)

        response = self.client.post(
            reverse("admin:micboard_settingdefinition_change", args=[definition.pk]),
            {
                "key": definition.key,
                "label": definition.label,
                "description": "Updated through admin",
                "scope": SettingDefinition.SCOPE_GLOBAL,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "choices_json": "{}",
                "default_value": "15",
                "is_active": "on",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SettingsRegistry.get("poll_interval"), 15)

    def test_setting_delete_invalidates_cached_value(self) -> None:
        """Deleting a stored override must expose its definition default immediately."""
        definition = SettingDefinition.objects.create(
            key="cache_timeout",
            label="Cache timeout",
            setting_type=SettingDefinition.TYPE_INTEGER,
            default_value="30",
        )
        setting = Setting.objects.create(definition=definition, value="60")
        self.assertEqual(SettingsRegistry.get("cache_timeout"), 60)

        response = self.client.post(
            reverse("admin:micboard_setting_delete", args=[setting.pk]),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Setting.objects.filter(pk=setting.pk).exists())
        self.assertEqual(SettingsRegistry.get("cache_timeout"), 30)


class SettingDefinitionTransitionFormTests(TestCase):
    """Definition edits must not invalidate already stored overrides."""

    def test_form_rejects_incompatible_scope_and_type_changes(self) -> None:
        """Model validation must surface transition failures on their form fields."""
        definition = SettingDefinition.objects.create(
            key="transition_contract",
            label="Transition contract",
            scope=SettingDefinition.SCOPE_GLOBAL,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="text",
        )
        Setting.objects.create(definition=definition, value="not-an-integer")
        form = SettingDefinitionForm(
            instance=definition,
            data={
                "key": definition.key,
                "label": definition.label,
                "description": "",
                "scope": SettingDefinition.SCOPE_SITE,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "1",
                "choices_json": "{}",
                "is_active": "on",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("scope", form.errors)
        self.assertIn("setting_type", form.errors)


@override_settings(
    MICBOARD_MSP_ENABLED=False,
    MICBOARD_MULTI_SITE_MODE=True,
    SITE_ID=7,
)
class MultiSiteSuperuserSettingsAdminTests(TestCase):
    """Superusers remain inside the current non-MSP site boundary."""

    def setUp(self) -> None:
        self.current_site = Site.objects.update_or_create(
            pk=7,
            defaults={"domain": "current.example.test", "name": "Current Site"},
        )[0]
        self.foreign_site = Site.objects.create(
            domain="foreign.example.test",
            name="Foreign Site",
        )
        self.definition = SettingDefinition.objects.create(
            key="site_private_value",
            label="Site private value",
            scope=SettingDefinition.SCOPE_SITE,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="default",
        )
        self.current_setting = Setting.objects.create(
            definition=self.definition,
            site=self.current_site,
            value="current-value",
        )
        self.foreign_setting = Setting.objects.create(
            definition=self.definition,
            site=self.foreign_site,
            value="foreign-value",
        )
        self.client = Client()
        self.client.force_login(UserFactory(is_staff=True, is_superuser=True))

    def test_admin_queryset_and_site_selector_use_only_current_site(self) -> None:
        """List and add surfaces must enforce the same current-site boundary."""
        list_response = self.client.get(reverse("admin:micboard_setting_changelist"))
        add_response = self.client.get(reverse("admin:micboard_setting_add"))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            {setting.pk for setting in list_response.context["cl"].result_list},
            {self.current_setting.pk},
        )
        self.assertNotContains(list_response, "foreign-value")
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(
            set(
                add_response.context["adminform"]
                .form.fields["site"]
                .queryset.values_list("pk", flat=True)
            ),
            {self.current_site.pk},
        )


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=True,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
class TenantSettingsAdminAccessTests(TestCase):
    """Tenant operators may manage only exact visible setting scopes."""

    def setUp(self) -> None:
        self.user = UserFactory(is_staff=True)
        permissions = Permission.objects.filter(
            content_type__app_label="micboard",
            codename__in=("add_setting", "change_setting", "view_setting"),
        )
        self.user.user_permissions.add(*permissions)
        self.inventory = create_tenant_inventory(self.user)
        site_settings = self.settings(SITE_ID=self.inventory.allowed_site.pk)
        site_settings.enable()
        self.addCleanup(site_settings.disable)
        self.definition = SettingDefinition.objects.create(
            key="TENANT_PRIVATE_VALUE",
            label="Tenant private value",
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="private-default",
        )
        self.allowed_rows: set[int] = set()
        campus_limited_organization_row = Setting.objects.create(
            definition=self.definition,
            organization_id=self.inventory.allowed_organization.pk,
            value="campus-limited-org-secret",
        )
        self.denied_rows = {
            campus_limited_organization_row.pk,
            Setting.objects.create(
                definition=self.definition,
                value="global-secret",
            ).pk,
            Setting.objects.create(
                definition=self.definition,
                organization_id=self.inventory.foreign_organization.pk,
                value="foreign-org-secret",
            ).pk,
            Setting.objects.create(
                definition=self.definition,
                site=self.inventory.allowed_site,
                value="allowed-site-secret",
            ).pk,
            Setting.objects.create(
                definition=self.definition,
                site=self.inventory.foreign_site,
                value="foreign-site-secret",
            ).pk,
            Setting.objects.create(
                definition=self.definition,
                manufacturer_id=self.inventory.allowed_manufacturer.pk,
                value="allowed-manufacturer-secret",
            ).pk,
            Setting.objects.create(
                definition=self.definition,
                manufacturer_id=self.inventory.foreign_manufacturer.pk,
                value="foreign-manufacturer-secret",
            ).pk,
        }
        self.client = Client()
        self.client.force_login(self.user)

    def test_standard_admin_queryset_excludes_global_and_foreign_rows(self) -> None:
        """Admin list visibility must match writable tenant scope."""
        response = self.client.get(reverse("admin:micboard_setting_changelist"))

        self.assertEqual(response.status_code, 200)
        result_ids = {setting.pk for setting in response.context["cl"].result_list}
        self.assertEqual(result_ids, self.allowed_rows)
        self.assertTrue(result_ids.isdisjoint(self.denied_rows))

    def test_standard_admin_rejects_global_and_foreign_scope_posts(self) -> None:
        """Forged add requests must not create global or foreign settings."""
        add_url = reverse("admin:micboard_setting_add")
        attempts = (
            {
                "definition": self.definition.pk,
                "organization_id": "",
                "site": "",
                "manufacturer_id": "",
                "value": "forged-global-secret",
                "_save": "Save",
            },
            {
                "definition": self.definition.pk,
                "organization_id": self.inventory.foreign_organization.pk,
                "site": "",
                "manufacturer_id": "",
                "value": "forged-foreign-secret",
                "_save": "Save",
            },
            {
                "definition": self.definition.pk,
                "organization_id": "",
                "site": "",
                "manufacturer_id": self.inventory.allowed_manufacturer.pk,
                "value": "forged-shared-manufacturer-secret",
                "_save": "Save",
            },
        )

        for payload in attempts:
            with self.subTest(payload=payload):
                response = self.client.post(add_url, payload)
                self.assertEqual(response.status_code, 200)

        self.assertFalse(Setting.objects.filter(value__startswith="forged-").exists())

    def test_standard_admin_hides_and_rejects_foreign_change_target(self) -> None:
        """A guessed foreign setting PK must not expose or mutate its row."""
        foreign_setting = Setting.objects.get(value="foreign-org-secret")
        original_value = foreign_setting.value
        change_url = reverse("admin:micboard_setting_change", args=[foreign_setting.pk])

        get_response = self.client.get(change_url)
        post_response = self.client.post(
            change_url,
            {
                "definition": foreign_setting.definition_id,
                "organization_id": foreign_setting.organization_id or "",
                "site": foreign_setting.site_id or "",
                "manufacturer_id": foreign_setting.manufacturer_id or "",
                "value": "foreign-row-overwrite",
                "_save": "Save",
            },
        )

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(post_response.status_code, 302)
        foreign_setting.refresh_from_db()
        self.assertEqual(foreign_setting.value, original_value)

    def test_standard_admin_scope_choices_exclude_foreign_targets(self) -> None:
        """Admin selectors must not offer IDs outside current tenant scope."""
        response = self.client.get(reverse("admin:micboard_setting_add"))

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        organization_ids = {
            value for value, _label in form.fields["organization_id"].choices if value != ""
        }
        manufacturer_ids = {
            value for value, _label in form.fields["manufacturer_id"].choices if value != ""
        }
        self.assertEqual(organization_ids, set())
        self.assertEqual(manufacturer_ids, set())
        self.assertEqual(
            set(form.fields["site"].queryset.values_list("pk", flat=True)),
            set(),
        )

    def test_campus_limited_membership_rejects_organization_setting(self) -> None:
        """Campus-only staff cannot mutate settings shared by sibling campuses."""
        definition = SettingDefinition.objects.create(
            key="CAMPUS_CANNOT_WRITE_ORGANIZATION",
            label="Campus cannot write organization",
            scope=SettingDefinition.SCOPE_ORGANIZATION,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="organization-default",
        )

        response = self.client.post(
            reverse("admin:micboard_setting_add"),
            {
                "definition": definition.pk,
                "organization_id": self.inventory.allowed_organization.pk,
                "site": "",
                "manufacturer_id": "",
                "value": "campus-forged-value",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Setting.objects.filter(value="campus-forged-value").exists())

    def test_standard_admin_accepts_allowed_organization_scope(self) -> None:
        """Tenant enforcement must preserve valid scoped administration."""
        self.user.org_memberships.update(campus=None)
        definition = SettingDefinition.objects.create(
            key="ANOTHER_TENANT_PRIVATE_VALUE",
            label="Another tenant private value",
            scope=SettingDefinition.SCOPE_ORGANIZATION,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="another-private-default",
        )

        response = self.client.post(
            reverse("admin:micboard_setting_add"),
            {
                "definition": definition.pk,
                "organization_id": self.inventory.allowed_organization.pk,
                "site": "",
                "manufacturer_id": "",
                "value": "allowed-new-secret",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Setting.objects.filter(
                definition=definition,
                organization_id=self.inventory.allowed_organization.pk,
                value="allowed-new-secret",
            ).exists()
        )

    def test_standard_admin_rejects_definition_scope_mismatch(self) -> None:
        """An authorized target cannot be used with a definition for another scope."""
        definition = SettingDefinition.objects.create(
            key="ORGANIZATION_ONLY_VALUE",
            label="Organization only value",
            scope=SettingDefinition.SCOPE_ORGANIZATION,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="organization-default",
        )

        response = self.client.post(
            reverse("admin:micboard_setting_add"),
            {
                "definition": definition.pk,
                "organization_id": "",
                "site": self.inventory.allowed_site.pk,
                "manufacturer_id": "",
                "value": "wrong-scope-value",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Setting.objects.filter(value="wrong-scope-value").exists())

    def test_bulk_form_ignores_definitions_from_another_scope(self) -> None:
        """A forged dynamic field cannot persist a definition under the wrong scope."""
        self.user.org_memberships.update(campus=None)
        global_definition = SettingDefinition.objects.create(
            key="GLOBAL_ONLY_VALUE",
            label="Global only value",
            scope=SettingDefinition.SCOPE_GLOBAL,
            setting_type=SettingDefinition.TYPE_STRING,
            default_value="global-default",
        )
        form = BulkSettingConfigForm(
            data={
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "organization": self.inventory.allowed_organization.pk,
                f"setting_{global_definition.pk}": "forged-bulk-value",
            },
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        result = form.save_settings()

        self.assertEqual(result["saved"], 0)
        self.assertFalse(Setting.objects.filter(value="forged-bulk-value").exists())

    def test_request_forms_receive_user_and_limit_choices(self) -> None:
        """Dedicated settings views must pass tenant context into both forms."""
        request = RequestFactory().get("/settings/")
        request.user = self.user
        bulk_view = BulkSettingConfigView()
        bulk_view.setup(request)
        manufacturer_view = ManufacturerSettingsView()
        manufacturer_view.setup(request)

        bulk_kwargs = bulk_view.get_form_kwargs()
        manufacturer_kwargs = manufacturer_view.get_form_kwargs()
        self.assertIs(bulk_kwargs["user"], self.user)
        self.assertIs(manufacturer_kwargs["user"], self.user)

        bulk_form = BulkSettingConfigForm(**bulk_kwargs)
        manufacturer_form = ManufacturerSettingsForm(**manufacturer_kwargs)
        scope_choices = {value for value, _label in bulk_form.fields["scope"].choices}
        self.assertNotIn(SettingDefinition.SCOPE_GLOBAL, scope_choices)
        self.assertNotIn(SettingDefinition.SCOPE_ORGANIZATION, scope_choices)
        self.assertNotIn(SettingDefinition.SCOPE_SITE, scope_choices)
        self.assertNotIn(SettingDefinition.SCOPE_MANUFACTURER, scope_choices)
        self.assertEqual(
            set(bulk_form.fields["organization"].queryset.values_list("pk", flat=True)),
            set(),
        )
        self.assertEqual(
            set(bulk_form.fields["site"].queryset.values_list("pk", flat=True)),
            set(),
        )
        self.assertEqual(
            set(manufacturer_form.fields["manufacturer"].queryset.values_list("pk", flat=True)),
            set(),
        )
