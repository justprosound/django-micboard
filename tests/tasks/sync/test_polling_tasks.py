"""Native Huey polling task wrapper contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.sync.polling_dtos import ManufacturerSyncResult
from micboard.tasks.sync.polling import (
    poll_api_server_device,
    poll_manufacturer_devices,
    refresh_selected_chassis,
)


def test_refresh_selected_chassis_serializes_service_result() -> None:
    """The task boundary returns a worker-safe dictionary from the service DTO."""
    result = Mock()
    result.model_dump.return_value = {"synced_count": 2, "failed_count": 1}
    with patch(
        "micboard.services.hardware.chassis_refresh_service."
        "ChassisRefreshService.refresh_authorized_ids",
        return_value=result,
    ) as refresh:
        assert refresh_selected_chassis([1, 2, 3], 17, using="replica") == {
            "synced_count": 2,
            "failed_count": 1,
        }

    refresh.assert_called_once_with(chassis_ids=[1, 2, 3], actor_id=17, using="replica")


def test_api_server_poll_task_handles_deleted_rows() -> None:
    """Queued server-target identifiers are safe after either row is deleted."""
    with patch(
        "micboard.tasks.sync.polling.ManufacturerAPIServer.objects.get",
        side_effect=ManufacturerAPIServer.DoesNotExist,
    ):
        assert poll_api_server_device(71, 72) is None


def test_api_server_poll_task_redacts_credentialed_transport_failure(caplog) -> None:
    """Worker logs retain IDs and exception type without vendor secrets."""
    server = SimpleNamespace(pk=71)
    chassis = SimpleNamespace(pk=72)
    chassis_scope = Mock()
    chassis_scope.get.return_value = chassis
    secret = "private-server-token"
    with (
        patch(
            "micboard.tasks.sync.polling.ManufacturerAPIServer.objects.get",
            return_value=server,
        ),
        patch(
            "micboard.tasks.sync.polling.WirelessChassis.objects.select_related",
            return_value=chassis_scope,
        ),
        patch(
            "micboard.services.sync.polling_api.APIServerPollingService.poll_managed_device",
            side_effect=RuntimeError(secret),
        ),
    ):
        assert poll_api_server_device(71, 72) is None

    assert secret not in caplog.text
    assert "managed chassis 72" in caplog.text
    assert "RuntimeError" in caplog.text


def test_repeated_polling_runs_alerts_without_enqueuing_realtime_supervisors() -> None:
    """Repeated polls cannot multiply long-running realtime worker tasks."""
    manufacturer = Mock(id=7, name="Vendor", code="vendor")
    sync_result = ManufacturerSyncResult(
        success=True, devices_added=2, devices_updated=1, devices_examined=3, device_limit=100
    )
    scan_result = SimpleNamespace(failed=0, scanned=2)
    with (
        patch(
            "micboard.tasks.sync.polling.Manufacturer.objects.get",
            return_value=manufacturer,
        ),
        patch(
            "micboard.services.manufacturer.sync.ManufacturerSyncService."
            "sync_devices_for_manufacturer",
            return_value=sync_result,
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service."
            "PollAlertService.evaluate_manufacturer",
            return_value=scan_result,
        ) as alert_scan,
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        assert poll_manufacturer_devices(7) == sync_result.model_dump()
        assert poll_manufacturer_devices(7) == sync_result.model_dump()

    assert alert_scan.call_args_list == [call(manufacturer), call(manufacturer)]
    enqueue.assert_not_called()


def test_poll_task_handles_missing_manufacturer() -> None:
    """Deleted or inactive manufacturer IDs are safe no-ops for queued tasks."""
    with patch(
        "micboard.tasks.sync.polling.Manufacturer.objects.get",
        side_effect=Manufacturer.DoesNotExist,
    ) as get_manufacturer:
        assert poll_manufacturer_devices(99) is None

    get_manufacturer.assert_called_once_with(pk=99, is_active=True)


def test_forced_poll_task_reloads_inactive_manufacturer_by_primary_key() -> None:
    """An explicit operator force override survives the async queue boundary."""
    manufacturer = Mock(id=7, name="Vendor", code="vendor")
    sync_result = ManufacturerSyncResult(success=True, device_limit=100)
    sync = Mock(return_value=sync_result)
    scan_result = SimpleNamespace(failed=0, scanned=0)
    with (
        patch(
            "micboard.tasks.sync.polling.Manufacturer.objects.get",
            return_value=manufacturer,
        ) as get_manufacturer,
        patch(
            "micboard.services.manufacturer.sync.ManufacturerSyncService."
            "sync_devices_for_manufacturer",
            sync,
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service."
            "PollAlertService.evaluate_manufacturer",
            return_value=scan_result,
        ),
    ):
        assert poll_manufacturer_devices(7, force=True) == sync_result.model_dump()

    get_manufacturer.assert_called_once_with(pk=7)
    assert sync.call_args.kwargs == {"manufacturer_code": "vendor", "force": True}


def test_poll_task_contains_and_redacts_service_failures(caplog) -> None:
    """Polling exceptions cannot crash the worker or disclose transport details."""
    manufacturer = Mock(id=7, name="Vendor", code="vendor")
    secret = "private-polling-credential"
    with (
        patch(
            "micboard.tasks.sync.polling.Manufacturer.objects.get",
            return_value=manufacturer,
        ),
        patch(
            "micboard.services.manufacturer.sync.ManufacturerSyncService."
            "sync_devices_for_manufacturer",
            Mock(side_effect=RuntimeError(secret)),
        ),
    ):
        assert poll_manufacturer_devices(7) is None

    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_a_failed_sync_skips_alert_evaluation_and_reports_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poll that failed has no fresh inventory, so evaluating alerts reads stale state."""
    manufacturer = SimpleNamespace(pk=3, code="vendor", name="Vendor")
    monkeypatch.setattr(
        Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        "micboard.services.manufacturer.sync.ManufacturerSyncService.sync_devices_for_manufacturer",
        Mock(
            return_value=ManufacturerSyncResult(
                success=False,
                errors=["Plugin not found: vendor"],
                device_limit=64,
            )
        ),
    )
    evaluate = Mock()
    monkeypatch.setattr(
        "micboard.services.monitoring.poll_alert_service.PollAlertService.evaluate_manufacturer",
        evaluate,
    )

    result = poll_manufacturer_devices(3)

    evaluate.assert_not_called()
    assert result is not None
    assert result["success"] is False
