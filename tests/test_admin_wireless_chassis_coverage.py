"""Coverage for wireless-chassis admin workflows."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

import pytest

from micboard.admin import receivers
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit


def _request(method: str = "get", data: dict[str, Any] | None = None) -> Any:
    request = getattr(RequestFactory(), method)("/admin/", data or {})
    request.user = SimpleNamespace(
        pk=4,
        is_authenticated=True,
        is_superuser=True,
        is_staff=True,
        has_perm=Mock(return_value=True),
    )
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_wireless_chassis_admin_delete_queryset_uses_locked_rows_and_one_bulk_hook() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    request = _request()
    queryset = MagicMock(db="default")
    queryset.values_list.return_value = [2, 1]
    locked = MagicMock()
    locked.using.return_value.select_for_update.return_value.filter.return_value.order_by.return_value = [
        "first",
        "second",
    ]
    deletion_queryset = object()
    locked.using.return_value.filter.return_value = deletion_queryset
    with (
        patch.object(receivers.WirelessChassis._meta, "default_manager", locked),
        patch.object(receivers.transaction, "atomic", return_value=nullcontext()),
        patch(
            "micboard.model_lifecycle.suppress_chassis_delete_hooks",
            return_value=nullcontext(),
        ),
        patch(
            "micboard.services.core.hardware_post_save_hooks.HardwarePostSaveHooks.handle_chassis_bulk_delete"
        ) as hook,
        patch.object(MicboardModelAdmin, "delete_queryset") as delete,
    ):
        model_admin.delete_queryset(request, queryset)
    hook.assert_called_once_with(chassis_list=["first", "second"], using="default")
    delete.assert_called_once_with(request, deletion_queryset)


def test_wireless_chassis_admin_queryset_counts_and_inline_battery() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    queryset = MagicMock()
    with patch.object(MicboardModelAdmin, "get_queryset", return_value=queryset):
        assert model_admin.get_queryset(_request()) is queryset.annotate.return_value
    assert model_admin.channel_count_display(SimpleNamespace(_channel_count=4)) == 4
    assert model_admin.channel_count_display(SimpleNamespace()) == 0
    assert model_admin.active_units_display(SimpleNamespace(_active_units_count=2)) == 2
    assert model_admin.active_units_display(SimpleNamespace()) == 0
    inline = receivers.WirelessUnitInline(WirelessUnit, AdminSite())
    with patch.object(receivers, "get_battery_percentage", return_value=75):
        assert inline.battery_percentage(object()) == 75


def _layout_chassis(*, manufacturer: Any, ip: str | None, channels: list[Any]) -> Any:
    channel_manager = MagicMock()
    channel_manager.all.return_value.order_by.return_value = channels
    return SimpleNamespace(manufacturer=manufacturer, ip=ip, rf_channels=channel_manager)


def test_wireless_chassis_hardware_layout_groups_units_and_unknowns() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    model_admin.admin_site.admin_view = Mock(side_effect=lambda view: view)
    with patch.object(MicboardModelAdmin, "get_urls", return_value=["base"]):
        assert len(model_admin.get_urls()) == 2
    with (
        patch.object(model_admin, "has_view_permission", return_value=False),
        pytest.raises(PermissionDenied),
    ):
        model_admin.hardware_layout_view(_request())

    unit = SimpleNamespace(frequency=500)
    first = _layout_chassis(
        manufacturer=SimpleNamespace(name="Vendor"),
        ip="192.0.2.1",
        channels=[
            SimpleNamespace(channel_number=1, active_wireless_unit=unit, active_iem_receiver=None),
            SimpleNamespace(channel_number=2, active_wireless_unit=None, active_iem_receiver=None),
        ],
    )
    second = _layout_chassis(
        manufacturer=None,
        ip=None,
        channels=[
            SimpleNamespace(
                channel_number=1,
                active_wireless_unit=None,
                active_iem_receiver=SimpleNamespace(frequency=None),
            )
        ],
    )
    queryset = MagicMock()
    queryset.filter.return_value.select_related.return_value.prefetch_related.return_value.annotate.return_value.order_by.return_value = [
        first,
        second,
    ]
    with (
        patch.object(model_admin, "has_view_permission", return_value=True),
        patch.object(model_admin, "get_queryset", return_value=queryset),
        patch.object(receivers, "render", return_value=HttpResponse()) as render,
    ):
        assert model_admin.hardware_layout_view(_request()).status_code == 200
    grouped = render.call_args.args[2]["grouped_chassis"]
    assert grouped["Vendor"]["192.0.2.1"][0]["channels"][0]["frequency"] == 500
    assert grouped["Unknown"]["Unknown IP"][0]["channels"][0]["frequency"] is None


def test_wireless_chassis_display_summary_changelist_and_status_paths() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    assert (
        model_admin.manufacturer_display(
            SimpleNamespace(manufacturer=SimpleNamespace(name="Vendor"))
        )
        == "Vendor"
    )
    assert model_admin.manufacturer_display(SimpleNamespace(manufacturer=None)) == "Unknown"
    assigned = MagicMock()
    assigned.filter.return_value.exists.return_value = True
    assigned.filter.return_value.first.return_value.user.username = "alice"
    unassigned = MagicMock()
    unassigned.filter.return_value.exists.return_value = False
    channels = [
        SimpleNamespace(
            channel_number=1,
            active_wireless_unit=SimpleNamespace(device_type="tx"),
            active_iem_receiver=None,
            assignments=assigned,
        ),
        SimpleNamespace(
            channel_number=2,
            active_wireless_unit=None,
            active_iem_receiver=None,
            assignments=unassigned,
        ),
    ]
    manager = MagicMock()
    manager.select_related.return_value.prefetch_related.return_value.order_by.return_value = (
        channels
    )
    assert model_admin.get_hardware_summary(SimpleNamespace(rf_channels=manager)) == (
        "CH1: TX → alice | CH2: No Unit → Unassigned"
    )
    with patch.object(MicboardModelAdmin, "changelist_view", return_value=HttpResponse()) as view:
        model_admin.changelist_view(_request())
        context = {"existing": True}
        model_admin.changelist_view(_request(), context)
    assert view.call_args_list[0].args[-1]["hardware_layout_url"] == "hardware-layout/"
    assert context["hardware_layout_url"] == "hardware-layout/"
    assert "Online" in model_admin.status_indicator(SimpleNamespace(is_online=True))
    assert "Offline" in model_admin.status_indicator(SimpleNamespace(is_online=False))


def test_wireless_chassis_online_offline_actions_delegate_sync_service() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    model_admin.message_user = Mock()
    chassis = [object(), object()]
    with patch(
        "micboard.services.core.hardware_sync.HardwareSyncService.sync_hardware_status"
    ) as sync:
        model_admin.mark_online(_request(), chassis)
        model_admin.mark_offline(_request(), chassis)
    assert sync.call_count == 4
    assert model_admin.message_user.call_count == 2


def _sync_queryset(ids: list[int]) -> MagicMock:
    queryset = MagicMock(db="replica")
    queryset.order_by.return_value.values_list.return_value = ids
    return queryset


def test_wireless_chassis_sync_action_empty_huey_limit_and_local_results() -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    model_admin.message_user = Mock()
    request = _request()
    with patch("micboard.utils.dependencies.huey_is_configured", return_value=False):
        model_admin.sync_from_api(request, _sync_queryset([]))
    assert "No chassis" in model_admin.message_user.call_args.args[1]

    model_admin.message_user.reset_mock()
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=True),
        patch("micboard.utils.dependencies.enqueue_huey_task") as enqueue,
    ):
        model_admin.sync_from_api(request, _sync_queryset([1, 2]))
    assert enqueue.call_args.args[1] == [1, 2]

    model_admin.message_user.reset_mock()
    with patch("micboard.utils.dependencies.huey_is_configured", return_value=False):
        model_admin.sync_from_api(
            request, _sync_queryset(list(range(receivers.MAX_SYNCHRONOUS_REFRESH + 1)))
        )
    assert "must be configured" in model_admin.message_user.call_args.args[1]

    model_admin.message_user.reset_mock()
    result = SimpleNamespace(synced_count=2, failed_count=1)
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=False),
        patch(
            "micboard.services.hardware.chassis_refresh_service.ChassisRefreshService.refresh",
            return_value=result,
        ),
    ):
        model_admin.sync_from_api(request, _sync_queryset([1, 2, 3]))
    assert model_admin.message_user.call_count == 2

    model_admin.message_user.reset_mock()
    with (
        patch("micboard.utils.dependencies.huey_is_configured", return_value=False),
        patch(
            "micboard.services.hardware.chassis_refresh_service.ChassisRefreshService.refresh",
            return_value=SimpleNamespace(synced_count=0, failed_count=0),
        ),
    ):
        model_admin.sync_from_api(request, _sync_queryset([1]))
    model_admin.message_user.assert_not_called()


@pytest.mark.parametrize(
    ("has_plan", "name", "expected"),
    [(False, "", "—"), (True, "G50", "G50"), (True, "", "470-534 MHz")],
)
def test_wireless_chassis_band_plan_display_paths(has_plan: bool, name: str, expected: str) -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    obj = SimpleNamespace(
        band_plan_name=name,
        band_plan_min_mhz=470,
        band_plan_max_mhz=534,
    )
    with patch(
        "micboard.services.hardware.wireless_chassis_service.get_band_plan_status",
        return_value=has_plan,
    ):
        assert expected in model_admin.band_plan_display(obj)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"has_band_plan": False}, "No band plan"),
        ({"has_band_plan": True, "needs_update": True}, "Missing coverage"),
        ({"has_band_plan": True, "needs_update": False, "has_coverage": True}, "OK"),
        ({"has_band_plan": True, "needs_update": False, "has_coverage": False}, "—"),
    ],
)
def test_wireless_chassis_regulatory_display_paths(status: dict[str, Any], expected: str) -> None:
    model_admin = _admin(receivers.WirelessChassisAdmin, WirelessChassis)
    with patch(
        "micboard.services.hardware.chassis_regulatory_service.get_band_plan_regulatory_status",
        return_value=status,
    ):
        assert expected in model_admin.band_plan_regulatory_status_display(object())
