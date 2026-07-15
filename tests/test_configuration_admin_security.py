"""Security coverage for manufacturer configuration administration."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.test import Client, RequestFactory
from django.urls import reverse

import pytest

from micboard.admin.configuration import (
    ConfigurationAuditLogAdmin,
    ManufacturerConfigurationAdmin,
)
from micboard.admin.manufacturers import ManufacturerAdmin, ManufacturerAdminForm
from micboard.forms.configuration import ManufacturerConfigurationForm
from micboard.models.audit.configuration_log import ConfigurationAuditLog
from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.manufacturer.secret_redaction import REDACTED_VALUE, redact_secrets
from micboard.views.settings import ManufacturerSettingsView


@pytest.mark.django_db
def test_configuration_form_masks_and_preserves_nested_secrets() -> None:
    """An edit can change safe values without receiving stored credentials."""
    private_key = "private-manufacturer-secret"
    configuration = ManufacturerConfiguration.objects.create(
        code="shure",
        name="Shure",
        config={
            "SHURE_API_SHARED_KEY": private_key,
            "timeout": 10,
            "nested": {"access_token": "nested-private-token", "enabled": True},
        },
    )

    unbound_form = ManufacturerConfigurationForm(instance=configuration)
    rendered = unbound_form["config"].as_widget()
    assert private_key not in rendered
    assert "nested-private-token" not in rendered
    assert REDACTED_VALUE in rendered

    submitted_config = redact_secrets(configuration.config)
    submitted_config["timeout"] = 20
    form = ManufacturerConfigurationForm(
        instance=configuration,
        data={
            "code": configuration.code,
            "name": configuration.name,
            "is_active": "on",
            "config": json.dumps(submitted_config),
            "updated_by": "",
        },
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["config"] == {
        "SHURE_API_SHARED_KEY": private_key,
        "timeout": 20,
        "nested": {"access_token": "nested-private-token", "enabled": True},
    }


def test_configuration_audit_admin_redacts_payloads_and_disables_transfer() -> None:
    """Audit screens retain useful context without rendering credential values."""
    configuration = ManufacturerConfiguration(code="shure", name="Shure")
    audit = ConfigurationAuditLog(
        configuration=configuration,
        old_values={"api_key": "old-private", "timeout": 5},
        new_values={"api_key": "new-private", "timeout": 10},
    )
    model_admin = ConfigurationAuditLogAdmin(ConfigurationAuditLog, AdminSite())
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True))

    old_display = model_admin.old_values_redacted(audit)
    new_display = model_admin.new_values_redacted(audit)
    assert "old-private" not in old_display
    assert "new-private" not in new_display
    assert REDACTED_VALUE in old_display
    assert REDACTED_VALUE in new_display
    assert "timeout" in old_display
    assert not model_admin.has_import_permission(request)
    assert not model_admin.has_export_permission(request)


def test_configuration_admin_disables_secret_import_and_export() -> None:
    """Manufacturer configuration cannot leave through generic transfer tools."""
    model_admin = ManufacturerConfigurationAdmin(ManufacturerConfiguration, AdminSite())
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True))

    assert not model_admin.has_import_permission(request)
    assert not model_admin.has_export_permission(request)


@pytest.mark.django_db
def test_manufacturer_admin_uses_persisted_settings_link_and_masks_config() -> None:
    """Manufacturer change pages contain only model fields and a real settings workflow."""
    private_key = "manufacturer-model-private-key"
    manufacturer = Manufacturer.objects.create(
        name="Secure Manufacturer",
        code="secure-manufacturer",
        config={"api_key": private_key, "timeout": 4},
    )
    user = User.objects.create_superuser(username="manufacturer-platform-admin")
    request = RequestFactory().get(f"/admin/micboard/manufacturer/{manufacturer.pk}/change/")
    request.user = user
    model_admin = ManufacturerAdmin(Manufacturer, AdminSite())

    form_class = model_admin.get_form(request, manufacturer)
    form = form_class(instance=manufacturer)
    rendered = form["config"].as_widget()
    assert private_key not in rendered
    assert REDACTED_VALUE in rendered
    assert set(form.fields) == {"name", "code", "is_active", "config"}
    assert "?manufacturer=" in model_admin.settings_link(manufacturer)
    assert model_admin.check() == []

    submitted = ManufacturerAdminForm(
        instance=manufacturer,
        data={
            "name": manufacturer.name,
            "code": manufacturer.code,
            "is_active": "on",
            "config": json.dumps({"api_key": REDACTED_VALUE, "timeout": 8}),
        },
    )
    assert submitted.is_valid(), submitted.errors
    assert submitted.cleaned_data["config"] == {"api_key": private_key, "timeout": 8}


def test_manufacturer_settings_link_preselects_requested_manufacturer() -> None:
    """The dedicated settings view consumes the admin link's initial selection."""
    view = ManufacturerSettingsView()
    view.request = RequestFactory().get("/settings/manufacturer/?manufacturer=42")

    assert view.get_initial()["manufacturer"] == "42"


@pytest.mark.django_db
def test_manufacturer_admin_runs_model_save_side_effects_once() -> None:
    """Admin persistence must not replay the model's lifecycle service."""
    manufacturer = Manufacturer(name="Single Save", code="single-save")
    model_admin = ManufacturerAdmin(Manufacturer, AdminSite())

    with patch("micboard.services.manufacturer.signals.handle_manufacturer_save") as handle_save:
        model_admin.save_model(Mock(), manufacturer, Mock(), change=False)

    handle_save.assert_called_once_with(
        manufacturer=manufacturer,
        created=True,
        old_active=False,
        using="default",
    )


@pytest.mark.django_db
def test_manufacturer_admin_runs_model_delete_side_effects_once() -> None:
    """Admin deletion must rely on the model's single lifecycle service call."""
    manufacturer = Manufacturer.objects.create(name="Single Delete", code="single-delete")
    model_admin = ManufacturerAdmin(Manufacturer, AdminSite())

    with patch(
        "micboard.services.manufacturer.signals.handle_manufacturer_delete"
    ) as handle_delete:
        model_admin.delete_model(Mock(), manufacturer)

    handle_delete.assert_called_once_with(manufacturer=manufacturer, using="default")


@pytest.mark.django_db
def test_view_only_configuration_admins_render_only_redacted_json() -> None:
    """Readonly admin rendering cannot reveal model JSON behind masked forms."""
    configuration_secret = "readonly-configuration-secret"
    manufacturer_secret = "readonly-manufacturer-secret"
    configuration = ManufacturerConfiguration.objects.create(
        code="readonly-config",
        name="Readonly Config",
        config={"shared_key": configuration_secret, "timeout": 10},
    )
    manufacturer = Manufacturer.objects.create(
        name="Readonly Manufacturer",
        code="readonly-manufacturer",
        config={"api_key": manufacturer_secret, "timeout": 5},
    )
    user = User.objects.create_user(username="configuration-viewer", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="view_manufacturerconfiguration"),
        Permission.objects.get(codename="view_manufacturer"),
    )
    client = Client()
    client.force_login(user)

    responses = (
        client.get(
            reverse(
                "admin:micboard_manufacturerconfiguration_change",
                args=[configuration.pk],
            )
        ),
        client.get(reverse("admin:micboard_manufacturer_change", args=[manufacturer.pk])),
    )

    for response in responses:
        assert response.status_code == 200
        content = response.content.decode()
        assert configuration_secret not in content
        assert manufacturer_secret not in content
        assert REDACTED_VALUE in content
