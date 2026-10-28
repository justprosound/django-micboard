"""What the poll_devices command reports to an operator.

The command's output is the only view most operators get of a poll, so it has to describe
what the poll actually did. The manufacturer inventory sync persists chassis; wireless units
are written by the realtime and managed-device paths, not by this one.
"""

from io import StringIO
from unittest.mock import Mock

from django.core.management import call_command

import pytest

from micboard.services.core.hardware import NormalizedChassis
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.services.sync.polling_dtos import ManufacturerSyncResult
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.fake_vendor import FakeVendorPlugin, use_vendor

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
    manufacturer = ManufacturerFactory(code="vendor", name="Vendor")
    payloads = [_payload_at(index) for index in range(created + updated)]
    for payload in payloads[created:]:
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=payload.api_device_id,
            serial_number=payload.serial_number,
            mac_address=payload.mac_address,
            ip=payload.ip,
        )
    use_vendor(monkeypatch, FakeVendorPlugin(payloads))
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


def _payload_at(index: int) -> NormalizedChassis:
    """Build the vendor payload for the nth distinct chassis."""
    return _payload(
        api_device_id=f"device-{index}",
        ip=f"192.0.2.{100 + index}",
        serial_number=f"serial-{index}",
        mac_address=f"00:11:22:33:44:{index:02x}",
    )


def _payload(**overrides: object) -> NormalizedChassis:
    """Build one normalized vendor payload."""
    values: dict[str, object] = {
        "api_device_id": "device-1",
        "ip": "192.0.2.100",
        "serial_number": "serial-1",
        "mac_address": "00:11:22:33:44:55",
        "name": "Receiver",
        "model": "RX-1",
        "role": "receiver",
        "firmware_version": "1.0",
        "hosted_firmware_version": "1.1",
        "description": "Rack receiver",
        "subnet_mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "network_mode": "static",
        "interface_id": "eth0",
    }
    values.update(overrides)
    return NormalizedChassis(**values)  # type: ignore[arg-type]


def test_a_failed_poll_is_reported_as_an_error_not_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync that returns success=False must not be printed as a successful summary.

    `sync_devices_for_manufacturer` reports expected failures — a missing integration, an
    inventory over its limit, a manufacturer deactivated mid-poll — in the result rather than
    by raising, so the command has to read it.
    """
    ManufacturerFactory(code="vendor", name="Vendor")
    monkeypatch.setattr(
        ManufacturerSyncService,
        "sync_devices_for_manufacturer",
        Mock(
            return_value=ManufacturerSyncResult(
                success=False,
                errors=["Plugin not found: vendor"],
                device_limit=64,
            )
        ),
    )
    out, err = StringIO(), StringIO()

    call_command("poll_devices", "--manufacturer", "vendor", stdout=out, stderr=err)

    assert "Success" not in out.getvalue()
    assert "vendor" in err.getvalue()


def test_a_failed_poll_does_not_leak_its_error_detail_to_the_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure messages reach the log, while the console stays free of vendor payloads."""
    secret = "bearer-token-77"
    ManufacturerFactory(code="vendor", name="Vendor")
    monkeypatch.setattr(
        ManufacturerSyncService,
        "sync_devices_for_manufacturer",
        Mock(
            return_value=ManufacturerSyncResult(
                success=False,
                errors=[secret],
                device_limit=64,
            )
        ),
    )
    err = StringIO()

    call_command("poll_devices", "--manufacturer", "vendor", stdout=StringIO(), stderr=err)

    assert secret not in err.getvalue()
