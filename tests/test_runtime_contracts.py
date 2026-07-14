"""Regression tests for runtime contracts caught by strict mypy checks."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.utils import timezone

import pytest

from micboard.integrations.shure.websocket import _read_and_dispatch_messages
from micboard.management.commands.realtime_status import Command as RealtimeStatusCommand
from micboard.models.audit import ActivityLog
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.maintenance.audit import AuditService
from micboard.services.maintenance.logging_mode import LoggingModeService
from micboard.services.realtime.shure_websocket_subscription_service import (
    run_shure_websocket_subscriptions,
)
from micboard.services.sync.device_promotion_service import DevicePromotionService
from micboard.services.sync.device_update_service import DeviceUpdateService


def test_websocket_dispatch_awaits_async_callback() -> None:
    """Hardware WebSocket callbacks can safely perform async update work."""
    received: list[dict[str, str]] = []

    async def messages():
        yield '{"status": "online"}'

    async def callback(payload: dict[str, str]) -> None:
        received.append(payload)

    asyncio.run(_read_and_dispatch_messages(messages(), "device-1", callback))

    assert received == [{"status": "online"}]


def test_duplicate_promotion_handles_empty_normalization() -> None:
    """Duplicate promotion fails cleanly when plugin data cannot be normalized."""
    manufacturer = object()
    discovered = SimpleNamespace(manufacturer=manufacturer)
    plugin = Mock()
    plugin.transform_device_data.return_value = {
        "serial_number": "serial",
        "mac_address": "00:00:00:00:00:01",
        "ip": "192.0.2.60",
        "api_device_id": "device-60",
    }
    dedup_result = SimpleNamespace(
        is_conflict=False,
        is_duplicate=True,
        existing_device=object(),
    )

    with (
        patch(
            "micboard.services.deduplication.check.check_device",
            return_value=dedup_result,
        ),
        patch(
            "micboard.services.manufacturer.sync.ManufacturerSyncService._normalize_devices",
            return_value=[],
        ),
    ):
        result = DevicePromotionService()._attempt_promotion_with_device_data(
            discovered,
            plugin,
            {"id": "device-60"},
        )

    assert result == (False, "Failed to normalize duplicate device data", None)


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

    lifecycle = Mock()
    lifecycle.mark_offline.side_effect = lambda receiver, **_kwargs: WirelessChassis.objects.filter(
        pk=receiver.pk
    ).update(status="offline")

    with (
        patch(
            "micboard.services.core.hardware_lifecycle.get_lifecycle_manager",
            return_value=lifecycle,
        ),
        patch(
            "micboard.services.sync.device_update_service.check_hardware_offline_alerts"
        ) as check_alerts,
    ):
        DeviceUpdateService.mark_offline_receivers(
            manufacturer=manufacturer,
            active_chassis_ids=[],
        )

    check_alerts.assert_called_once()
    assert check_alerts.call_args.args[0] == unit


def test_websocket_service_instantiates_plugin_and_uses_chassis_status() -> None:
    """WebSocket startup honors plugin-class and WirelessChassis field contracts."""
    manufacturer = Mock(pk=14, code="shure", name="Shure")
    plugin_class = Mock()

    with (
        patch(
            "micboard.models.discovery.manufacturer.Manufacturer.objects.get",
            return_value=manufacturer,
        ) as get_manufacturer,
        patch(
            "micboard.services.realtime.shure_websocket_subscription_service."
            "get_manufacturer_plugin",
            return_value=plugin_class,
        ),
        patch(
            "micboard.models.hardware.wireless_chassis.WirelessChassis.objects.filter",
            return_value=[],
        ) as filter_chassis,
        patch(
            "micboard.services.realtime.shure_websocket_subscription_service."
            "RealtimeSubscriptionSupervisor.select_fair_queryset_batch",
            return_value=[],
        ),
    ):
        run_shure_websocket_subscriptions(14)

    get_manufacturer.assert_called_once_with(pk=14, code="shure", is_active=True)
    plugin_class.assert_called_once_with(manufacturer)
    filter_chassis.assert_called_once_with(
        manufacturer_id=14,
        manufacturer__is_active=True,
        status__in=("online", "degraded", "provisioning"),
    )


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
        connection_duration=None,
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
