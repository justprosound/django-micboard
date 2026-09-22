"""What the poll_devices command reports to an operator.

The command's output is the only view most operators get of a poll, so it has to describe
what the poll actually did. The manufacturer inventory sync persists chassis; wireless units
are written by the realtime and managed-device paths, not by this one.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import Mock

from django.core.management import call_command

import pytest

from micboard.services.core.hardware import NormalizedHardware
from micboard.services.manufacturer.sync import ManufacturerSyncService
from tests.factories.discovery import ManufacturerFactory

pytestmark = pytest.mark.django_db


def _poll(
    monkeypatch: pytest.MonkeyPatch,
    *,
    created: int = 0,
    updated: int = 0,
) -> str:
    """Run the command over a stubbed vendor, so the real poll path runs underneath.

    Only the vendor boundary is substituted: plugin construction and inventory
    normalisation. Persistence, auditing, broadcasting, and reporting are the real thing.
    """
    ManufacturerFactory(code="vendor", name="Vendor")
    devices = [{"id": f"raw-{index}"} for index in range(created + updated)]
    plugin = Mock()
    plugin.get_devices.return_value = devices

    outcomes = ["created"] * created + ["updated"] * updated
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.PluginRegistry.get_plugin",
        Mock(return_value=plugin),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_normalize_devices",
        Mock(return_value=[_payload(api_device_id=f"device-{i}") for i in range(len(devices))]),
    )
    monkeypatch.setattr(
        ManufacturerSyncService,
        "_sync_normalized_device",
        Mock(side_effect=outcomes),
    )
    monkeypatch.setattr(
        "micboard.services.notification.device_broadcast_service."
        "DeviceSnapshotBroadcastService.broadcast",
        Mock(return_value=None),
    )

    out = StringIO()
    call_command("poll_devices", "--manufacturer", "vendor", stdout=out, stderr=StringIO())
    return out.getvalue()


def test_poll_reports_the_chassis_counts_it_produced(monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator needs the created and updated counts the sync actually returned."""
    output = _poll(monkeypatch, created=2, updated=3)

    assert "2 created" in output
    assert "3 updated" in output


def test_poll_makes_no_claim_about_wireless_units(monkeypatch: pytest.MonkeyPatch) -> None:
    """This poll never writes wireless units, so reporting a count would be a false report."""
    output = _poll(monkeypatch, created=2, updated=3)

    assert "wireless unit" not in output.lower()
    assert "transmitter" not in output.lower()


def test_a_poll_records_its_created_count_in_the_audit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audit row is the durable record of a poll, so its counts must match the sync's."""
    from micboard.models.audit.activity_log import ServiceSyncLog

    _poll(monkeypatch, created=2, updated=3)

    row = ServiceSyncLog.objects.latest("pk")
    assert row.updated_count == 3
    assert row.device_count == 5
    assert row.details["created_count"] == 2


def _payload(**overrides: object) -> NormalizedHardware:
    """Build one normalized vendor payload."""
    values: dict[str, object] = {
        "api_device_id": "device-1",
        "ip": "192.0.2.100",
        "serial_number": "serial-1",
        "mac_address": "00:11:22:33:44:55",
        "name": "Receiver",
        "model": "RX-1",
        "device_type": "receiver",
        "firmware_version": "1.0",
        "hosted_firmware_version": "1.1",
        "description": "Rack receiver",
        "subnet_mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "network_mode": "static",
        "interface_id": "eth0",
    }
    values.update(overrides)
    return NormalizedHardware(**values)  # type: ignore[arg-type]
