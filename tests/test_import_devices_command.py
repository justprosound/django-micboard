"""Behavioral coverage for the device import command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import Mock

import pytest

from micboard.management.commands import import_devices as import_devices_command


def test_import_devices_reports_missing_configuration(monkeypatch) -> None:
    settings_get = Mock(side_effect=[{}, "https://localhost:10000", None])
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings.get",
        settings_get,
    )
    output = StringIO()
    command = import_devices_command.Command(stdout=output)

    command.handle(server_id=None, dry_run=False, full=False)

    assert "No API servers configured" in output.getvalue()


def test_import_devices_rejects_unknown_server(monkeypatch) -> None:
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings.get",
        Mock(return_value={"known": {"manufacturer": "shure"}}),
    )
    output = StringIO()
    command = import_devices_command.Command(stdout=output)
    command.handle(server_id="missing", dry_run=False, full=False)
    assert "Server ID 'missing' not found" in output.getvalue()


def test_import_devices_delegates_and_prints_dry_run_summary(monkeypatch) -> None:
    servers = {"primary": {"manufacturer": "shure"}, "backup": {"manufacturer": "shure"}}
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings.get",
        Mock(return_value=servers),
    )
    manufacturer = object()
    monkeypatch.setattr(
        import_devices_command.Manufacturer.objects,
        "get_or_create",
        Mock(return_value=(manufacturer, False)),
    )
    service = Mock()
    service.import_from_servers.return_value = (5, 2, 3)
    monkeypatch.setattr(
        "micboard.services.import_service.ImportService", Mock(return_value=service)
    )
    output = StringIO()
    command = import_devices_command.Command(stdout=output)

    command.handle(server_id="primary", dry_run=True, full=False)

    assert service.import_from_servers.call_args.kwargs["api_servers"] == {
        "primary": servers["primary"]
    }
    assert service.import_from_servers.call_args.kwargs["manufacturer"] is manufacturer
    assert "Total discovered: 5" in output.getvalue()
    assert "DRY RUN" in output.getvalue()


def test_import_devices_builds_default_server_from_legacy_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings.get",
        Mock(side_effect=[{}, "https://api.test", "secret"]),
    )
    manufacturer = object()
    monkeypatch.setattr(
        import_devices_command.Manufacturer.objects,
        "get_or_create",
        Mock(return_value=(manufacturer, False)),
    )
    service = Mock()
    service.import_from_servers.return_value = (0, 0, 0)
    monkeypatch.setattr(
        "micboard.services.import_service.ImportService", Mock(return_value=service)
    )

    import_devices_command.Command(stdout=StringIO()).handle(
        server_id=None, dry_run=False, full=False
    )

    assert service.import_from_servers.call_args.kwargs["api_servers"] == {
        "default": {
            "manufacturer": "shure",
            "base_url": "https://api.test",
            "shared_key": "secret",
            "location_id": None,
        }
    }


@pytest.mark.parametrize(
    ("device", "result", "dry_run", "expected"),
    [
        ({"name": "missing"}, (False, False), False, "Skipping device"),
        ({"serial": "NEW"}, (True, False), True, "Would create"),
        ({"serialNumber": "OLD"}, (False, True), True, "Would update"),
        ({"serial": "CONFLICT"}, (False, False), True, "Would skip"),
        ({"serial": "CREATED"}, (True, False), False, "Created"),
        ({"serial": "UPDATED"}, (False, True), False, "Updated"),
    ],
)
def test_import_device_detailed_output(
    monkeypatch, device, result, dry_run: bool, expected: str
) -> None:
    service = Mock()
    service.import_device.return_value = result
    monkeypatch.setattr(
        "micboard.services.import_service.ImportService", Mock(return_value=service)
    )
    output = StringIO()
    command = import_devices_command.Command(stdout=output)
    assert (
        command._import_device(
            device,
            object(),
            object(),
            "primary",
            dry_run=dry_run,
            full=True,
        )
        == result
    )
    assert expected in output.getvalue()
