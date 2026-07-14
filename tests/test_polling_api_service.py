"""Focused coverage for low-level API polling and discovery dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import PermissionDenied

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.integrations.api_server_service import APIServerConnectionService
from micboard.services.sync.discovery_trigger_service import trigger_discovery
from micboard.services.sync.polling_api import APIServerPollingService
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import ManufacturerAPIServerFactory, WirelessChassisFactory
from tests.factories.locations import LocationFactory


def _server(**overrides: Any) -> Any:
    """Build the API-server surface consumed by the polling service."""
    values = {
        "pk": 1,
        "name": "Main venue",
        "manufacturer": "shure",
        "status": ManufacturerAPIServer.Status.UNKNOWN,
        "enabled": True,
        "last_health_check": None,
        "status_message": "",
        "base_url": "https://audio.example.test",
        "shared_key": "row-specific-shared-key",
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_managed_poll_skips_unsupported_owned_server_without_transport() -> None:
    """An owned target for an unsupported vendor remains a transport-free no-op."""
    server = _server(
        manufacturer=ManufacturerAPIServer.Manufacturer.DANTE,
        location_name="Stage",
    )
    chassis = SimpleNamespace(
        api_device_id="dante-device",
        location_id=1,
        location=SimpleNamespace(name="Stage"),
        manufacturer=SimpleNamespace(code="dante"),
    )

    with (
        patch.object(APIServerPollingService, "_server_owns_chassis", return_value=True),
        patch.object(APIServerConnectionService, "fetch_server_devices") as fetch_devices,
    ):
        assert APIServerPollingService.poll_managed_device(server=server, chassis=chassis) == 0

    fetch_devices.assert_not_called()


def test_managed_poll_records_bounded_transport_failure() -> None:
    """A scoped transport error marks only its persisted server row unhealthy."""
    server = _server(location_name="Stage")
    chassis = SimpleNamespace(
        api_device_id="shure-device",
        location_id=1,
        location=SimpleNamespace(name="Stage"),
        manufacturer=SimpleNamespace(code="shure"),
    )
    with (
        patch.object(APIServerPollingService, "_server_owns_chassis", return_value=True),
        patch.object(
            APIServerConnectionService,
            "fetch_server_devices",
            side_effect=RuntimeError("private credential detail"),
        ),
        pytest.raises(RuntimeError, match="private credential detail"),
    ):
        APIServerPollingService.poll_managed_device(server=server, chassis=chassis)

    assert server.status == ManufacturerAPIServer.Status.ERROR
    assert server.status_message == "Polling failed (RuntimeError)"
    server.save.assert_called_once_with(update_fields=["status", "status_message"])


@pytest.mark.django_db
def test_managed_poll_rejects_ambiguous_location_name_before_transport() -> None:
    """A legacy name shared by tenants cannot establish API-server ownership."""
    manufacturer = ManufacturerFactory(code="shure")
    location = LocationFactory(name="Shared rack")
    LocationFactory(name="Shared rack")
    server = ManufacturerAPIServerFactory(
        manufacturer=ManufacturerAPIServer.Manufacturer.SHURE,
        location_name=location.name,
    )
    chassis = WirelessChassisFactory(
        manufacturer=manufacturer,
        location=location,
        api_device_id="owned-device",
    )

    with (
        patch.object(APIServerConnectionService, "fetch_server_devices") as fetch_devices,
        pytest.raises(PermissionDenied, match="does not own"),
    ):
        APIServerPollingService.poll_managed_device(server=server, chassis=chassis)

    fetch_devices.assert_not_called()


def test_managed_poll_rejects_blank_device_identity_before_transport() -> None:
    """A queued poll must identify one concrete vendor device before connecting."""
    server = _server(location_name="Stage")
    chassis = SimpleNamespace(api_device_id="", manufacturer=SimpleNamespace(code="shure"))

    with (
        patch.object(APIServerPollingService, "_server_owns_chassis", return_value=True),
        patch.object(APIServerConnectionService, "fetch_server_devices") as fetch_devices,
        pytest.raises(PermissionDenied, match="does not own"),
    ):
        APIServerPollingService.poll_managed_device(server=server, chassis=chassis)

    fetch_devices.assert_not_called()


@pytest.mark.parametrize("manufacturer_id", [None, 0])
@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch("micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust")
def test_trigger_discovery_rejects_missing_manufacturer_ids(
    send_request: MagicMock,
    _huey_configured: MagicMock,
    manufacturer_id: int | None,
) -> None:
    """Discovery dispatch must never enqueue an unscoped scan."""
    trigger_discovery(manufacturer_id)

    send_request.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=False)
@patch("micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust")
def test_trigger_discovery_skips_dispatch_without_huey(
    send_request: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Unconfigured native Huey is a safe no-op."""
    trigger_discovery(42)

    send_request.assert_not_called()


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch(
    "micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust",
    return_value=[(object(), None)],
)
def test_trigger_discovery_dispatches_full_scan(
    send_request: MagicMock,
    _huey_configured: MagicMock,
) -> None:
    """Configured discovery requests both CIDR and FQDN scans."""
    trigger_discovery(42)

    send_request.assert_called_once_with(
        sender=trigger_discovery,
        manufacturer_id=42,
        scan_cidrs=True,
        scan_fqdns=True,
    )


@patch("micboard.services.sync.discovery_trigger_service.huey_is_configured", return_value=True)
@patch("micboard.services.sync.discovery_trigger_service.discovery_requested.send_robust")
def test_trigger_discovery_redacts_dispatcher_exception(
    send_request: MagicMock,
    _huey_configured: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "dispatcher-secret-token\nforged-log-entry"
    send_request.return_value = [(object(), RuntimeError(secret))]

    with caplog.at_level("ERROR"):
        trigger_discovery(42)

    assert secret not in caplog.text
    assert "error details redacted" in caplog.text
