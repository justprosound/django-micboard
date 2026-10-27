"""Dispatch policy for an operator-selected chassis refresh."""

from unittest.mock import patch

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware import chassis_refresh_service
from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService
from micboard.tasks.sync.polling import (
    refresh_selected_chassis,
    request_selected_chassis_refresh,
)
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _selection(count: int):
    chassis = WirelessChassisFactory.create_batch(count)
    return WirelessChassis.objects.filter(pk__in=[item.pk for item in chassis]), sorted(
        item.pk for item in chassis
    )


def test_an_empty_selection_is_reported_without_dispatch() -> None:
    with patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue:
        result = request_selected_chassis_refresh(
            queryset=WirelessChassis.objects.none(),
            actor_id=1,
        )

    assert result.outcome == "empty"
    enqueue.assert_not_called()


def test_a_selection_over_the_batch_limit_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(chassis_refresh_service, "MAX_CHASSIS_REFRESH_BATCH", 2)
    queryset, _ = _selection(3)

    with patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue:
        result = request_selected_chassis_refresh(queryset=queryset, actor_id=1)

    assert result.outcome == "oversized"
    enqueue.assert_not_called()


def test_a_configured_queue_receives_the_exact_selected_ids() -> None:
    queryset, ids = _selection(2)

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        result = request_selected_chassis_refresh(queryset=queryset, actor_id=42)

    assert result.outcome == "queued"
    assert result.selected_count == 2
    enqueue.assert_called_once_with(refresh_selected_chassis, ids, 42, using="default")


def test_without_a_queue_a_large_selection_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(chassis_refresh_service, "MAX_SYNCHRONOUS_REFRESH", 1)
    queryset, _ = _selection(2)

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=False),
        patch.object(ChassisRefreshService, "refresh") as refresh,
    ):
        result = request_selected_chassis_refresh(queryset=queryset, actor_id=1)

    assert result.outcome == "needs_queue"
    refresh.assert_not_called()


def test_without_a_queue_a_small_selection_refreshes_in_process() -> None:
    queryset, _ = _selection(2)

    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=False),
        patch.object(
            ChassisRefreshService,
            "refresh",
            return_value=chassis_refresh_service.ChassisRefreshResult(
                synced_count=1, failed_count=1
            ),
        ) as refresh,
    ):
        result = request_selected_chassis_refresh(queryset=queryset, actor_id=1)

    refresh.assert_called_once()
    assert (result.outcome, result.synced_count, result.failed_count) == ("refreshed", 1, 1)
