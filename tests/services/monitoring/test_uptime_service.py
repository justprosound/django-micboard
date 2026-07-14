"""Service-level coverage for chassis uptime calculations."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

import pytest

from micboard.models.discovery.queue import DeviceMovementLog
from micboard.services.monitoring.uptime_service import BulkUptimeCalculator, UptimeService
from tests.factories.discovery import DeviceMovementLogFactory, ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


@pytest.fixture(autouse=True)
def isolate_chassis_lifecycle():
    """Keep uptime persistence independent of manufacturer and task transports."""
    with (
        override_settings(TESTING=True),
        patch(
            "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
            return_value=None,
        ),
    ):
        yield


@pytest.mark.django_db
def test_status_changes_write_once_and_accumulate_completed_session() -> None:
    """Only transitions write, and an online session contributes whole minutes."""
    device = WirelessChassisFactory(
        is_online=False,
        last_online_at=None,
        total_uptime_minutes=10,
    )
    online_at = timezone.now()

    with patch("micboard.services.monitoring.uptime_service.timezone.now", return_value=online_at):
        assert UptimeService.record_status_change(device, True)
        assert not UptimeService.record_status_change(device, True)

    assert device.last_online_at == online_at
    assert device.last_offline_at is None

    offline_at = online_at + timedelta(minutes=90, seconds=45)
    with patch("micboard.services.monitoring.uptime_service.timezone.now", return_value=offline_at):
        assert UptimeService.record_status_change(device, False)

    device.refresh_from_db()
    assert not device.is_online
    assert device.last_offline_at == offline_at
    assert device.total_uptime_minutes == 100


@pytest.mark.django_db
def test_offline_transition_without_start_time_preserves_total() -> None:
    """Missing session start data does not invent uptime."""
    device = WirelessChassisFactory(
        is_online=True,
        last_online_at=None,
        total_uptime_minutes=7,
    )

    assert UptimeService.record_status_change(device, False)

    assert device.total_uptime_minutes == 7
    assert device.last_offline_at is not None


@pytest.mark.django_db
def test_uptime_percentage_counts_acknowledged_and_bounded_unacknowledged_movements() -> None:
    """Movement downtime uses acknowledgement duration or a one-hour cap."""
    device = WirelessChassisFactory()
    current_time = timezone.now()
    acknowledged = DeviceMovementLogFactory(
        device=device,
        old_ip="192.0.2.10",
        new_ip="192.0.2.11",
    )
    unacknowledged = DeviceMovementLogFactory(
        device=device,
        old_ip="192.0.2.11",
        new_ip="192.0.2.12",
    )
    ignored = DeviceMovementLogFactory(device=device, old_ip=None, new_ip=None)
    DeviceMovementLog.objects.filter(pk=acknowledged.pk).update(
        detected_at=current_time - timedelta(hours=2),
        acknowledged_at=current_time - timedelta(minutes=90),
    )
    DeviceMovementLog.objects.filter(pk=unacknowledged.pk).update(
        detected_at=current_time - timedelta(minutes=30),
    )
    DeviceMovementLog.objects.filter(pk=ignored.pk).update(
        detected_at=current_time - timedelta(minutes=15),
    )

    with patch(
        "micboard.services.monitoring.uptime_service.timezone.now",
        return_value=current_time,
    ):
        percentage = UptimeService.get_uptime_percentage(device, days=1)
        assert UptimeService.get_uptime_percentage(device, days=0) == 100.0
        assert UptimeService.get_uptime_percentage(device, days=-1) == 100.0

    assert percentage == pytest.approx(95.8333, rel=1e-3)


def test_uptime_period_helpers_delegate_with_expected_days() -> None:
    """Period helpers keep one implementation for percentage calculation."""
    device = object()
    with patch.object(
        UptimeService,
        "get_uptime_percentage",
        side_effect=[97.0, 98.0],
    ) as get_percentage:
        assert UptimeService.get_uptime_percentage_7d(device) == 97.0
        assert UptimeService.get_uptime_percentage_30d(device) == 98.0

    assert [call.kwargs["days"] for call in get_percentage.call_args_list] == [7, 30]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("elapsed", "formatted", "minutes"),
    [
        (timedelta(minutes=45), "45m", 45),
        (timedelta(hours=2, minutes=5), "2h 5m", 125),
        (timedelta(days=1, hours=2, minutes=3), "1d 2h 3m", 1563),
    ],
)
def test_session_uptime_formats_elapsed_time(elapsed, formatted, minutes) -> None:
    """Live session summaries use compact minute, hour, and day labels."""
    current_time = timezone.now()
    device = WirelessChassisFactory(
        is_online=True,
        last_online_at=current_time - elapsed,
    )

    with patch(
        "micboard.services.monitoring.uptime_service.timezone.now",
        return_value=current_time,
    ):
        result = UptimeService.get_session_uptime(device)

    assert result["is_online"]
    assert result["uptime_minutes"] == minutes
    assert result["uptime_hours"] == minutes / 60
    assert result["uptime_formatted"] == formatted


@pytest.mark.django_db
def test_session_uptime_returns_offline_shape_without_active_start() -> None:
    """Offline and incomplete sessions return the same zeroed shape."""
    device = WirelessChassisFactory(is_online=False, last_online_at=None)

    assert UptimeService.get_session_uptime(device) == {
        "is_online": False,
        "uptime_minutes": 0,
        "uptime_hours": 0,
        "uptime_formatted": "Offline",
        "started_at": None,
    }

    device.is_online = True
    assert UptimeService.get_session_uptime(device)["uptime_formatted"] == "Offline"


@pytest.mark.django_db
def test_uptime_summary_combines_session_and_period_metrics() -> None:
    """Summary output preserves persisted timestamps and delegated metrics."""
    device = WirelessChassisFactory(total_uptime_minutes=42)
    with (
        patch.object(UptimeService, "get_session_uptime", return_value={"session": True}),
        patch.object(UptimeService, "get_uptime_percentage_7d", return_value=97.5),
        patch.object(UptimeService, "get_uptime_percentage_30d", return_value=98.5),
    ):
        summary = UptimeService.get_uptime_summary(device)

    assert summary == {
        "session": {"session": True},
        "total_minutes_tracked": 42,
        "uptime_7d_percent": 97.5,
        "uptime_30d_percent": 98.5,
        "last_online_at": device.last_online_at,
        "last_offline_at": device.last_offline_at,
    }


@pytest.mark.django_db
def test_batch_uptime_calculation_returns_each_device_percentage() -> None:
    """One movement query produces bounded percentages for every device."""
    first = WirelessChassisFactory()
    second = WirelessChassisFactory()
    current_time = timezone.now()
    movement = DeviceMovementLogFactory(
        device=first,
        old_ip="192.0.2.20",
        new_ip="192.0.2.21",
    )
    DeviceMovementLog.objects.filter(pk=movement.pk).update(
        detected_at=current_time - timedelta(hours=2),
        acknowledged_at=current_time - timedelta(hours=1),
    )
    recent_unacknowledged = DeviceMovementLogFactory(
        device=second,
        old_ip="192.0.2.22",
        new_ip="192.0.2.23",
    )
    DeviceMovementLog.objects.filter(pk=recent_unacknowledged.pk).update(
        detected_at=current_time - timedelta(minutes=30),
    )

    with patch(
        "micboard.services.monitoring.uptime_service.timezone.now",
        return_value=current_time,
    ):
        result = BulkUptimeCalculator.get_uptime_summary_batch([first, second], days=1)
        second_individual = UptimeService.get_uptime_percentage(second, days=1)

    assert result[first.pk] == pytest.approx(95.8333, rel=1e-3)
    assert result[second.pk] == pytest.approx(97.9167, rel=1e-3)
    assert result[second.pk] == second_individual


@pytest.mark.django_db
def test_non_positive_batch_window_reports_full_uptime_without_movement_queries(
    django_assert_num_queries,
) -> None:
    """Batch and fleet entry points match the single-device zero-window contract."""
    manufacturer = ManufacturerFactory()
    online = WirelessChassisFactory(manufacturer=manufacturer, is_online=True)
    offline = WirelessChassisFactory(manufacturer=manufacturer, is_online=False)

    with django_assert_num_queries(0):
        assert BulkUptimeCalculator.get_uptime_summary_batch([online, offline], days=0) == {
            online.pk: 100.0,
            offline.pk: 100.0,
        }

    with django_assert_num_queries(1):
        stats = BulkUptimeCalculator.get_manufacturer_uptime_stats(manufacturer, days=0)

    assert stats["average_uptime_percent"] == 100.0
    assert stats["min_uptime_percent"] == 100.0
    assert stats["max_uptime_percent"] == 100.0


@pytest.mark.django_db
def test_manufacturer_stats_cover_empty_and_populated_fleets(django_assert_num_queries) -> None:
    """Fleet aggregation reports counts, extrema, and per-device results."""
    empty_manufacturer = ManufacturerFactory()
    assert BulkUptimeCalculator.get_manufacturer_uptime_stats(empty_manufacturer) == {
        "total_devices": 0,
        "online_devices": 0,
        "offline_devices": 0,
        "average_uptime_percent": 0,
        "devices": {},
    }

    manufacturer = ManufacturerFactory()
    online = WirelessChassisFactory(manufacturer=manufacturer, is_online=True)
    offline = WirelessChassisFactory(manufacturer=manufacturer, is_online=False)
    percentages = {online.pk: 99.0, offline.pk: 91.0}

    with (
        patch.object(
            BulkUptimeCalculator,
            "get_uptime_summary_batch",
            return_value=percentages,
        ),
        django_assert_num_queries(1),
    ):
        stats = BulkUptimeCalculator.get_manufacturer_uptime_stats(manufacturer, days=30)

    assert stats == {
        "total_devices": 2,
        "online_devices": 1,
        "offline_devices": 1,
        "average_uptime_percent": 95.0,
        "min_uptime_percent": 91.0,
        "max_uptime_percent": 99.0,
        "devices": percentages,
    }
