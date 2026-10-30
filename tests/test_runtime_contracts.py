"""Regression tests for runtime contracts caught by strict mypy checks."""

import asyncio
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

import pytest

from micboard.integrations.shure.websocket import _read_and_dispatch_messages
from micboard.management.commands.realtime_status import Command as RealtimeStatusCommand
from micboard.models.audit.activity_log import ActivityLog
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.maintenance.audit import AuditService
from micboard.services.maintenance.logging_mode import LoggingModeService
from micboard.services.sync.chassis_ingest import ChassisIngestService, IngestMode


def test_websocket_dispatch_awaits_async_callback() -> None:
    """Hardware WebSocket callbacks can safely perform async update work."""
    received: list[dict[str, str]] = []

    async def messages():
        yield '{"status": "online"}'

    async def callback(payload: dict[str, str]) -> None:
        received.append(payload)

    asyncio.run(_read_and_dispatch_messages(messages(), "device-1", callback))

    assert received == [{"status": "online"}]


@pytest.mark.django_db
def test_offline_chassis_checks_attached_wireless_units() -> None:
    """Offline chassis alerts receive WirelessUnit objects, never RFChannel objects."""
    manufacturer = Manufacturer.objects.create(name="Runtime Vendor", code="runtime-vendor")
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="runtime-chassis",
        ip="192.0.2.50",
        role="receiver",
        status="online",
    )
    unit = WirelessUnit.objects.create(
        manufacturer=manufacturer,
        base_chassis=chassis,
        model="Runtime Unit",
        serial_number="runtime-unit",
        slot=1,
        status="online",
    )

    with patch(
        "micboard.services.sync.chassis_ingest.alert_manager.check_hardware_offline_alerts"
    ) as check_alerts:
        ChassisIngestService.ingest(
            [],
            manufacturer=manufacturer,
            mode=IngestMode.AUTHORITATIVE_SNAPSHOT,
        )

    check_alerts.assert_called_once()
    assert check_alerts.call_args.args[0] == unit


def test_set_logging_mode_converts_minutes_to_service_ttl() -> None:
    """CLI minutes are converted to LoggingModeService seconds."""
    stdout = StringIO()

    with patch.object(LoggingModeService, "set_mode") as set_mode:
        call_command("set_logging_mode", "high", "--duration", "2", stdout=stdout)

    set_mode.assert_called_once_with("high", ttl_seconds=120)
    assert "Duration: 2 minute(s)" in stdout.getvalue()


def test_realtime_status_query_and_output_use_chassis_relation() -> None:
    """Realtime status follows RealTimeConnection.chassis, not removed receiver."""
    queryset = RealtimeStatusCommand._get_connections("shure", "connected")
    str(queryset.query)

    stdout = StringIO()
    command = RealtimeStatusCommand(stdout=stdout)
    connection = SimpleNamespace(
        status="connected",
        chassis=SimpleNamespace(
            name="Rack 1",
            manufacturer=SimpleNamespace(name="Shure"),
        ),
        connected_at=None,
        last_message_at=None,
        error_message="",
        connected_duration=None,
    )
    command._write_connection(connection)

    assert "Shure - Rack 1: CONNECTED" in stdout.getvalue()


@pytest.mark.django_db
def test_archive_activity_logs_writes_csv_before_deleting(tmp_path: Path) -> None:
    """Audit archival preserves expired rows on disk before pruning them."""
    activity = ActivityLog.objects.create(
        activity_type=ActivityLog.ACTIVITY_CRUD,
        operation=ActivityLog.CREATE,
        summary="Runtime contract archive",
        details={"source": "test"},
    )
    ActivityLog.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=31)
    )

    result = AuditService.archive_activity_logs(retention_days=30, path=str(tmp_path))

    archive_path = Path(str(result["file"]))
    assert result["archived"] == 1
    assert archive_path.exists()
    assert "Runtime contract archive" in archive_path.read_text(encoding="utf-8")
    assert not ActivityLog.objects.filter(pk=activity.pk).exists()


def test_audit_retention_rejects_negative_days() -> None:
    """Invalid retention cannot accidentally archive or prune future records."""
    with pytest.raises(ValueError, match="zero or greater"):
        AuditService._resolve_retention_days(-1, default=30)
