"""Security coverage for credential-bearing manufacturer API servers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse

import pytest

from micboard.admin.integrations import ManufacturerAPIServerAdmin
from micboard.forms.integrations import ManufacturerAPIServerForm
from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.api_server_service import APIServerConnectionService


@pytest.mark.django_db
def test_api_server_form_never_renders_or_erases_stored_shared_key() -> None:
    """Editing a server treats the existing credential as write-only."""
    private_key = "private-row-shared-key"
    server = ManufacturerAPIServer.objects.create(
        name="Main venue",
        manufacturer=ManufacturerAPIServer.Manufacturer.SHURE,
        base_url="https://audio.example.test",
        shared_key=private_key,
    )

    unbound_form = ManufacturerAPIServerForm(instance=server)
    assert private_key not in unbound_form["shared_key"].as_widget()

    form = ManufacturerAPIServerForm(
        instance=server,
        data={
            "name": server.name,
            "manufacturer": server.manufacturer,
            "base_url": server.base_url,
            "shared_key": "",
            "location_name": "",
            "status": server.status,
            "status_message": "",
            "notes": "",
        },
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["shared_key"] == private_key


@pytest.mark.parametrize(
    "base_url",
    [
        "https://metadata.internal",
        "https://audio.example.test.attacker.invalid",
        "https://192.0.2.44",
    ],
)
@override_settings(MICBOARD_API_SERVER_ALLOWED_HOSTS=["audio.example.test"])
def test_api_server_destination_must_match_explicit_allowlist(base_url: str) -> None:
    """Admin-editable endpoints cannot target arbitrary server-side destinations."""
    with pytest.raises(ValidationError, match="MICBOARD_API_SERVER_ALLOWED_HOSTS"):
        APIServerConnectionService.validate_destination(base_url)


@override_settings(MICBOARD_API_SERVER_ALLOWED_HOSTS=["audio.example.test"])
@patch("micboard.integrations.shure.client.ShureSystemAPIClient")
def test_api_server_health_check_uses_row_credential_and_closes_client(
    client_class: MagicMock,
) -> None:
    """A health check cannot forward a process-global credential to a row URL."""
    client = client_class.return_value.__enter__.return_value
    client.devices.get_devices.return_value = [{"id": "one"}]
    server = SimpleNamespace(
        pk=9,
        base_url="https://audio.example.test:10000",
        shared_key="row-specific-key",
        manufacturer=ManufacturerAPIServer.Manufacturer.SHURE,
        status=ManufacturerAPIServer.Status.UNKNOWN,
        status_message="",
        last_health_check=None,
        save=Mock(),
    )

    APIServerConnectionService.test_connection(server)

    client_class.assert_called_once_with(
        base_url="https://audio.example.test:10000",
        shared_key="row-specific-key",
    )
    client_class.return_value.__exit__.assert_called_once()
    assert server.status == ManufacturerAPIServer.Status.ACTIVE
    server.save.assert_called_once()


def test_api_server_admin_disables_secret_import_and_export() -> None:
    """Bulk transfer surfaces cannot disclose persisted shared keys."""
    model_admin = ManufacturerAPIServerAdmin(ManufacturerAPIServer, AdminSite())
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True))

    assert not model_admin.has_import_permission(request)
    assert not model_admin.has_export_permission(request)


@pytest.mark.django_db
def test_view_only_api_server_admin_never_renders_shared_key() -> None:
    """Django's readonly fallback cannot bypass the write-only credential form."""
    private_key = "view-only-private-shared-key"
    server = ManufacturerAPIServer.objects.create(
        name="Readonly venue",
        manufacturer=ManufacturerAPIServer.Manufacturer.SHURE,
        base_url="https://readonly.example.test",
        shared_key=private_key,
    )
    user = User.objects.create_user(username="api-server-viewer", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_manufacturerapiserver"))
    client = Client()
    client.force_login(user)

    response = client.get(reverse("admin:micboard_manufacturerapiserver_change", args=[server.pk]))

    assert response.status_code == 200
    assert private_key not in response.content.decode()
    assert "••••••" in response.content.decode()
