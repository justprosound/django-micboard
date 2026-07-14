"""Admin dispatch coverage for bounded selected-chassis refreshes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.contrib.admin.sites import AdminSite

from micboard.admin.receivers import MAX_SYNCHRONOUS_REFRESH, WirelessChassisAdmin
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import ChassisRefreshResult
from micboard.tasks.sync.polling import refresh_selected_chassis


def _selection(*ids: int) -> MagicMock:
    queryset = MagicMock()
    queryset.db = "default"
    queryset.order_by.return_value.values_list.return_value = list(ids)
    return queryset


@patch("micboard.utils.dependencies.enqueue_huey_task")
@patch("micboard.utils.dependencies.huey_is_configured", return_value=True)
def test_admin_enqueues_exact_selected_ids_when_huey_is_configured(
    _huey_configured: MagicMock,
    enqueue: MagicMock,
) -> None:
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    model_admin.message_user = Mock()

    model_admin.sync_from_api(SimpleNamespace(), _selection(7, 9))

    enqueue.assert_called_once_with(refresh_selected_chassis, [7, 9], using="default")
    assert "Queued 2 chassis" in model_admin.message_user.call_args.args[1]


@patch("micboard.services.hardware.chassis_refresh_service.ChassisRefreshService.refresh_ids")
@patch("micboard.utils.dependencies.huey_is_configured", return_value=False)
def test_admin_refuses_unbounded_synchronous_refresh(
    _huey_configured: MagicMock,
    refresh_ids: MagicMock,
) -> None:
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    model_admin.message_user = Mock()
    ids = tuple(range(1, MAX_SYNCHRONOUS_REFRESH + 2))

    model_admin.sync_from_api(SimpleNamespace(), _selection(*ids))

    refresh_ids.assert_not_called()
    assert "Native Huey must be configured" in model_admin.message_user.call_args.args[1]


@patch("micboard.services.hardware.chassis_refresh_service.ChassisRefreshService.refresh_ids")
@patch("micboard.utils.dependencies.huey_is_configured", return_value=False)
def test_admin_fallback_refreshes_only_selected_ids(
    _huey_configured: MagicMock,
    refresh_ids: MagicMock,
) -> None:
    refresh_ids.return_value = ChassisRefreshResult(synced_count=2, failed_count=0)
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    model_admin.message_user = Mock()

    model_admin.sync_from_api(SimpleNamespace(), _selection(4, 5))

    refresh_ids.assert_called_once_with(chassis_ids=[4, 5], using="default")


@patch("micboard.services.hardware.chassis_refresh_service.ChassisRefreshService.refresh_ids")
def test_native_huey_task_preserves_ids_and_database_alias(refresh_ids: MagicMock) -> None:
    refresh_ids.return_value = ChassisRefreshResult(synced_count=1, failed_count=1)

    result = refresh_selected_chassis([3, 8], using="replica")

    assert result == {"synced_count": 1, "failed_count": 1}
    refresh_ids.assert_called_once_with(chassis_ids=[3, 8], using="replica")
