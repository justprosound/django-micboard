"""Coverage for polling orchestration, failure isolation, and health reporting."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.base_polling_mixin import (
    PollingMixin,
    PollSequenceExecutor,
    create_polling_complete_callback,
)
from micboard.services.sync.polling_service import PollingService, get_polling_service


def _manufacturer(code: str = "test") -> Any:
    return SimpleNamespace(code=code, name=code.title())


@patch.object(Manufacturer.objects, "filter")
def test_poll_all_aggregates_successes_and_errors(mock_filter: MagicMock) -> None:
    manufacturers = [_manufacturer("one"), _manufacturer("two")]
    mock_filter.return_value = MagicMock(
        count=Mock(return_value=2),
        __iter__=Mock(return_value=iter(manufacturers)),
    )
    handler = Mock(
        side_effect=[
            {"devices_created": 2, "devices_updated": 1, "units_synced": 3, "errors": []},
            {"devices_created": 0, "devices_updated": 1, "units_synced": 0, "errors": ["bad"]},
        ]
    )
    complete = Mock()
    result = PollingMixin().poll_all_manufacturers_with_handler(
        on_manufacturer_polled=handler,
        on_complete=complete,
    )
    assert result["summary"] == {
        "total_chassis_created": 2,
        "total_chassis_updated": 2,
        "total_wireless_units": 3,
        "total_errors": 1,
        "errors": ["bad"],
    }
    complete.assert_called_once_with(result)


@patch.object(Manufacturer.objects, "filter")
def test_poll_all_contains_handler_and_callback_failures(mock_filter: MagicMock) -> None:
    manufacturer = _manufacturer()
    mock_filter.return_value.count.return_value = 1
    mock_filter.return_value.__iter__.return_value = iter([manufacturer])
    error_handler = Mock(side_effect=RuntimeError("callback"))
    complete = Mock(side_effect=RuntimeError("complete"))
    result = PollingMixin().poll_all_manufacturers_with_handler(
        on_manufacturer_polled=Mock(side_effect=ValueError("poll")),
        on_error=error_handler,
        on_complete=complete,
    )
    assert result["manufacturers"]["test"] == {"status": "failed", "error": "poll"}
    assert result["summary"]["total_errors"] == 1


@patch.object(Manufacturer.objects, "filter")
def test_poll_all_without_handler_skips_unsupported_mixin(mock_filter: MagicMock) -> None:
    mock_filter.return_value.count.return_value = 1
    mock_filter.return_value.__iter__.return_value = iter([_manufacturer()])
    result = PollingMixin().poll_all_manufacturers_with_handler()
    assert result["manufacturers"] == {}


def test_polling_result_validation_and_health_normalization() -> None:
    mixin = PollingMixin()
    assert mixin._validate_polling_result(
        {"devices_created": 0, "devices_updated": 0, "units_synced": 0}
    )
    assert not mixin._validate_polling_result({"devices_created": 0})
    assert mixin._standardize_health_response({})["status"] == "error"
    assert mixin._standardize_health_response({"healthy": True})["status"] == "healthy"
    assert mixin._standardize_health_response({"healthy": False})["status"] == "degraded"
    assert mixin._standardize_health_response({"status": "unexpected"})["status"] == "unknown"


@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
@patch("channels.layers.get_channel_layer", return_value=object())
def test_polling_complete_signal_broadcasts(_layer: MagicMock, broadcast: MagicMock) -> None:
    manufacturer = _manufacturer()
    PollingMixin()._emit_polling_complete_signal(manufacturer, {"ok": True})
    broadcast.assert_called_once_with(manufacturer=manufacturer, data={"ok": True})


@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_api_health")
@patch("channels.layers.get_channel_layer", return_value=object())
def test_health_changed_signal_broadcasts(_layer: MagicMock, broadcast: MagicMock) -> None:
    manufacturer = _manufacturer()
    PollingMixin()._emit_health_changed_signal(manufacturer, {"status": "healthy"})
    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        health_data={"status": "healthy"},
    )


def test_poll_sequence_continues_or_stops_after_errors() -> None:
    executor = PollSequenceExecutor()
    executor.add_step("ok", lambda: {"count": 1})
    executor.add_step("bad", Mock(side_effect=RuntimeError("failed")))
    executor.add_step("later", lambda: {"count": 2})
    result = executor.execute()
    assert result["success"] is False
    assert result["results"] == {"ok": {"count": 1}, "later": {"count": 2}}
    assert result["errors"] == {"bad": "failed"}

    stopped = PollSequenceExecutor()
    stopped.add_step("bad", Mock(side_effect=RuntimeError("stop")))
    stopped.add_step("never", lambda: {})
    assert stopped.execute(stop_on_error=True)["completed_steps"] == 0


def test_polling_completion_callback_accepts_all_modes() -> None:
    create_polling_complete_callback()({"manufacturers": {"one": {}}})
    create_polling_complete_callback(broadcast_updates=False, run_alerts=False)({})


@patch.object(Manufacturer.objects, "all")
@patch.object(Manufacturer.objects, "filter")
def test_refresh_devices_maps_poll_results(mock_filter: MagicMock, mock_all: MagicMock) -> None:
    manufacturer = _manufacturer()
    mock_filter.return_value = [manufacturer]
    service = cast(Any, PollingService())
    service.poll_manufacturer = Mock(
        return_value={"devices_created": 1, "devices_updated": 2, "errors": []}
    )
    assert service.refresh_devices(manufacturer="test")["test"]["device_count"] == 3
    mock_filter.assert_called_once_with(code="test")

    mock_all.return_value = [manufacturer]
    service.poll_manufacturer.return_value = {"status": "failed", "errors": ["down"]}
    assert service.refresh_devices()["test"]["status"] == "error"


@patch("micboard.services.notification.signal_emitter.SignalEmitter.emit_devices_polled")
@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_emits_and_broadcasts(
    sync_devices: MagicMock,
    emit_devices_polled: MagicMock,
) -> None:
    manufacturer = _manufacturer()
    sync_devices.return_value = {"created": 2, "updated": 1, "error_messages": []}
    service = cast(Any, PollingService())
    service.broadcast_device_updates = Mock()
    result = service.poll_manufacturer(manufacturer)
    assert result["devices_created"] == 2
    assert result["devices_updated"] == 1
    service.broadcast_device_updates.assert_called_once_with(manufacturer, result)
    emit_devices_polled.assert_called_once_with(manufacturer, result)


@patch("micboard.services.sync.hardware_sync_service.HardwareSyncService.sync_devices")
def test_poll_manufacturer_contains_sync_failure(sync_devices: MagicMock) -> None:
    sync_devices.side_effect = RuntimeError("offline")
    result = PollingService().poll_manufacturer(_manufacturer())
    assert result["status"] == "failed"
    assert result["errors"] == ["offline"]


@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
@patch.object(WirelessChassis.objects, "filter")
def test_device_broadcast_serializes_active_chassis(
    chassis_filter: MagicMock,
    broadcast: MagicMock,
) -> None:
    chassis_filter.return_value = [
        SimpleNamespace(
            id=1,
            api_device_id="device-1",
            name="Receiver",
            ip="192.0.2.1",
            status="online",
            model="RX",
        )
    ]
    PollingService().broadcast_device_updates(_manufacturer(), {})
    payload = broadcast.call_args.kwargs["data"]
    assert payload["receivers"][0]["api_device_id"] == "device-1"
    assert payload["manufacturer_code"] == "test"


@patch("micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_update")
@patch.object(WirelessChassis.objects, "filter", return_value=[])
def test_device_broadcast_delegates_channel_handling(
    _chassis_filter: MagicMock,
    broadcast: MagicMock,
) -> None:
    PollingService().broadcast_device_updates(_manufacturer(), {})
    broadcast.assert_called_once()


@patch("micboard.services.notification.signal_emitter.SignalEmitter.emit_api_health_changed")
@patch("micboard.services.common.base.plugin.get_manufacturer_plugin")
def test_api_health_is_standardized_and_emitted(
    get_plugin: MagicMock,
    emit_health: MagicMock,
) -> None:
    client = SimpleNamespace(check_health=Mock(return_value={"healthy": True}))
    get_plugin.return_value.return_value.get_client.return_value = client
    manufacturer = _manufacturer()
    result = PollingService().check_api_health(manufacturer)
    assert result["status"] == "healthy"
    emit_health.assert_called_once_with(manufacturer, result)


@patch("micboard.services.notification.signal_emitter.SignalEmitter.emit_api_health_changed")
@patch(
    "micboard.services.common.base.plugin.get_manufacturer_plugin",
    side_effect=RuntimeError("bad api"),
)
def test_api_health_contains_client_errors(
    _get_plugin: MagicMock,
    emit_health: MagicMock,
) -> None:
    manufacturer = _manufacturer()
    result = PollingService().check_api_health(manufacturer)
    assert result["status"] == "error"
    emit_health.assert_called_once_with(manufacturer, result)


@patch.object(WirelessChassis.objects, "filter")
@patch.object(Manufacturer.objects, "filter")
@patch("micboard.services.common.base.plugin.get_manufacturer_plugin")
def test_polling_health_aggregates_device_and_api_state(
    get_plugin: MagicMock,
    manufacturer_filter: MagicMock,
    chassis_filter: MagicMock,
) -> None:
    manufacturer_filter.return_value = [_manufacturer()]
    all_chassis = MagicMock()
    all_chassis.count.return_value = 3
    active = MagicMock()
    active.count.return_value = 2
    online = MagicMock()
    online.count.return_value = 1
    online.exists.return_value = True
    all_chassis.filter.side_effect = [active]
    active.filter.return_value = online
    chassis_filter.return_value = all_chassis
    get_plugin.return_value.return_value.get_client.return_value.is_healthy.return_value = False
    result = PollingService().get_polling_health()
    assert result["overall_status"] == "degraded"
    assert result["summary"] == {
        "total_devices": 3,
        "online_devices": 1,
        "offline_devices": 2,
    }


def test_polling_service_factory_returns_fresh_service() -> None:
    assert isinstance(get_polling_service(), PollingService)
    assert isinstance(cast(Any, PollingService())._poll_manufacturer_handler, object)
