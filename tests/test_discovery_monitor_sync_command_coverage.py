"""Behavioral coverage for the discovery synchronization command."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, call

from micboard.management.commands import sync_discovery as sync_command


def test_sync_discovery_missing_and_empty_manufacturers(monkeypatch) -> None:
    output = StringIO()
    command = sync_command.Command(stdout=output)
    monkeypatch.setattr(
        sync_command.Manufacturer.objects,
        "get",
        Mock(side_effect=sync_command.Manufacturer.DoesNotExist),
    )
    command.handle(manufacturer="missing", scan_cidrs=False, scan_fqdns=False, max_hosts=10)
    assert "not found" in output.getvalue()

    monkeypatch.setattr(sync_command.Manufacturer.objects, "filter", Mock(return_value=[]))
    command.handle(manufacturer=None, scan_cidrs=False, scan_fqdns=False, max_hosts=10)
    assert "No active manufacturers" in output.getvalue()


def test_sync_discovery_reports_all_task_statuses(monkeypatch) -> None:
    manufacturers = [
        SimpleNamespace(id=1, name="One", code="one"),
        SimpleNamespace(id=2, name="Two", code="two"),
        SimpleNamespace(id=3, name="Three", code="three"),
    ]
    monkeypatch.setattr(
        sync_command.Manufacturer.objects,
        "filter",
        Mock(return_value=manufacturers),
    )
    run = Mock(
        side_effect=[
            {
                "status": "success",
                "created_receivers": 1,
                "missing_ips_submitted": 2,
                "scanned_ips_submitted": 3,
                "errors": ["warning"],
            },
            {"status": "failed"},
            {"status": "pending"},
        ]
    )
    monkeypatch.setattr(
        sync_command,
        "DiscoverySyncService",
        Mock(return_value=SimpleNamespace(run=run)),
    )
    output = StringIO()
    command = sync_command.Command(stdout=output)
    command.handle(manufacturer=None, scan_cidrs=True, scan_fqdns=True, max_hosts=20)
    text = output.getvalue()
    assert "Sync completed successfully" in text
    assert "Sync failed" in text
    assert "Status: pending" in text
    assert "warning" in text
    assert run.call_args_list[0] == call(
        1,
        add_cidrs=None,
        add_fqdns=None,
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=20,
    )


def test_sync_discovery_accepts_one_named_manufacturer(monkeypatch) -> None:
    manufacturer = SimpleNamespace(id=7, name="Vendor", code="vendor")
    monkeypatch.setattr(sync_command.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    run = Mock(return_value={"status": "success"})
    monkeypatch.setattr(
        sync_command,
        "DiscoverySyncService",
        Mock(return_value=SimpleNamespace(run=run)),
    )
    sync_command.Command(stdout=StringIO()).handle(
        manufacturer="vendor",
        scan_cidrs=False,
        scan_fqdns=False,
        max_hosts=10,
    )
    sync_command.Manufacturer.objects.get.assert_called_once_with(code="vendor")
