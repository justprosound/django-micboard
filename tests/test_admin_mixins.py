"""Regression tests for composing optional admin integrations."""

from typing import Any, cast
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from micboard.admin.integrations import AccessoryAdmin
from micboard.admin.mixins import HAS_IMPORT_EXPORT, MicboardModelAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import Charger
from micboard.models.integrations import Accessory
from micboard.utils.dependencies import (
    HAS_UNFOLD,
    HAS_UNFOLD_FILTERS,
    HAS_UNFOLD_IMPORT_EXPORT,
    is_django_app_configured,
)


def test_unconfigured_import_export_uses_core_admin_template() -> None:
    """An importable but unconfigured integration must not select its templates."""
    model_admin = cast(Any, admin.site._registry[Charger])

    assert HAS_IMPORT_EXPORT is False
    assert model_admin.change_list_template is None


def test_accessory_admin_is_registered_on_the_live_site() -> None:
    """The accessory management surface must be reachable through Django admin."""
    assert isinstance(admin.site._registry[Accessory], AccessoryAdmin)


def test_django_app_detection_requires_host_configuration() -> None:
    """Package availability must not substitute for host app registration."""
    assert is_django_app_configured("micboard") is True
    assert is_django_app_configured("import_export") is False


def test_base_admin_disables_unscoped_bulk_data_transfer() -> None:
    """Optional import-export routes stay closed without request-aware resources."""
    model_admin = MicboardModelAdmin(Manufacturer, AdminSite())
    request = RequestFactory().get("/admin/micboard/manufacturer/")

    assert model_admin.has_import_permission(request) is False
    assert model_admin.has_export_permission(request) is False


def test_pre_setup_app_detection_does_not_confuse_nested_apps() -> None:
    """A configured child app must not imply that its parent app is enabled."""
    with (
        patch.object(apps, "apps_ready", False),
        patch.object(settings, "INSTALLED_APPS", ["unfold.contrib.filters"]),
        patch("micboard.utils.dependencies.is_installed", return_value=True),
    ):
        assert is_django_app_configured("unfold") is False


def test_pre_setup_app_detection_accepts_explicit_app_config() -> None:
    """Hosts may configure an integration through its AppConfig class path."""
    with (
        patch.object(apps, "apps_ready", False),
        patch.object(settings, "INSTALLED_APPS", ["micboard.apps.MicboardConfig"]),
    ):
        assert is_django_app_configured("micboard") is True


def test_unfold_contrib_features_require_their_base_integrations() -> None:
    """Contrib features must stay disabled unless every parent app is active."""
    assert HAS_UNFOLD is False
    assert HAS_UNFOLD_FILTERS is False
    assert HAS_UNFOLD_IMPORT_EXPORT is False
