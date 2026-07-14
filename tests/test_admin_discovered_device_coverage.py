"""Coverage for discovered-device admin workflows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

import pytest

from micboard.admin import monitoring
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.discovery.registry import DiscoveredDevice
from tests.factories.discovery import DiscoveredDeviceFactory, ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


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


def _discovered(**overrides: Any) -> Any:
    defaults = {
        "pk": 2,
        "ip": "192.0.2.2",
        "manufacturer": SimpleNamespace(code="vendor"),
        "status": DiscoveredDevice.STATUS_READY,
        "STATUS_READY": DiscoveredDevice.STATUS_READY,
        "STATUS_PENDING": DiscoveredDevice.STATUS_PENDING,
        "STATUS_INCOMPATIBLE": DiscoveredDevice.STATUS_INCOMPATIBLE,
        "STATUS_ERROR": DiscoveredDevice.STATUS_ERROR,
        "STATUS_OFFLINE": DiscoveredDevice.STATUS_OFFLINE,
        "_is_managed": False,
        "get_status_display": lambda: "Custom",
        "delete": Mock(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_discovered_device_admin_queryset_status_protocol_and_management_flags() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    queryset = MagicMock()
    with patch.object(MicboardModelAdmin, "get_queryset", return_value=queryset):
        assert (
            model_admin.get_queryset(_request())
            is queryset.select_related.return_value.annotate.return_value
        )
    queryset.select_related.assert_called_once_with("manufacturer")
    assert "_is_managed" in queryset.select_related.return_value.annotate.call_args.kwargs
    for status, expected in (
        (DiscoveredDevice.STATUS_READY, "Ready"),
        (DiscoveredDevice.STATUS_PENDING, "Pending"),
        ("custom", "Custom"),
    ):
        assert expected in model_admin.status_display_with_color(_discovered(status=status))
    with patch.object(monitoring, "get_device_communication_protocol", side_effect=["HTTP", None]):
        assert model_admin.protocol_display(_discovered()) == "HTTP"
        assert model_admin.protocol_display(_discovered()) == "—"
    assert model_admin.is_managed_display(_discovered(_is_managed=True)) is True
    with patch.object(monitoring, "is_device_manageable", return_value=True):
        assert model_admin.is_manageable_display(_discovered()) is True


@pytest.mark.parametrize(
    ("manageable", "reason", "promotion", "expected"),
    [
        (True, None, (True, ""), "ready"),
        (False, "unsupported", (False, ""), "unsupported"),
        (False, None, (False, "missing config"), "missing config"),
        (False, None, (True, ""), "unknown"),
    ],
)
def test_discovered_device_manageability_detail_paths(
    manageable: bool, reason: str | None, promotion: tuple[bool, str], expected: str
) -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    with (
        patch.object(monitoring, "is_device_manageable", return_value=manageable),
        patch.object(monitoring, "get_device_incompatibility_reason", return_value=reason),
        patch.object(monitoring, "can_promote_device_to_chassis", return_value=promotion),
    ):
        assert expected.lower() in model_admin.manageable_status_detail(_discovered()).lower()


@pytest.mark.parametrize(
    ("managed", "promotion", "manageable", "expected"),
    [
        (True, (True, ""), True, "Already Managed"),
        (False, (False, "unsupported"), True, "Cannot Promote"),
        (False, (True, ""), False, "Not Ready"),
        (False, (True, ""), True, "Promote to Chassis"),
    ],
)
def test_discovered_device_promotion_action_paths(
    managed: bool, promotion: tuple[bool, str], manageable: bool, expected: str
) -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    with (
        patch.object(monitoring, "can_promote_device_to_chassis", return_value=promotion),
        patch.object(monitoring, "is_device_manageable", return_value=manageable),
        patch.object(monitoring, "reverse", return_value="/promote/"),
    ):
        assert expected in model_admin.promotion_actions(_discovered(_is_managed=managed))


@pytest.mark.django_db
def test_discovered_device_management_columns_share_one_bounded_query() -> None:
    user = get_user_model().objects.create_superuser(username="discovered-device-query-admin")
    request = RequestFactory().get("/admin/micboard/discovereddevice/")
    request.user = user
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    manufacturer = ManufacturerFactory()
    managed = DiscoveredDeviceFactory(manufacturer=manufacturer)
    WirelessChassisFactory(
        manufacturer=manufacturer,
        ip=managed.ip,
        max_channels=0,
    )

    def render_columns() -> tuple[int, list[tuple[bool, str]], list[str]]:
        with (
            patch.object(monitoring, "can_promote_device_to_chassis", return_value=(True, "")),
            patch.object(monitoring, "is_device_manageable", return_value=True),
            patch.object(monitoring, "reverse", return_value="/promote/"),
            CaptureQueriesContext(connection) as query_context,
        ):
            devices = list(model_admin.get_queryset(request).order_by("pk"))
            columns = [
                (
                    model_admin.is_managed_display(device),
                    str(model_admin.promotion_actions(device)),
                )
                for device in devices
            ]
        return len(query_context), columns, [query["sql"] for query in query_context]

    small_count, small_columns, _small_queries = render_columns()
    DiscoveredDeviceFactory.create_batch(5, manufacturer=manufacturer)
    large_count, large_columns, large_queries = render_columns()

    assert small_columns == [(True, "✓ Already Managed")]
    assert len(large_columns) == 6
    assert large_columns.count((True, "✓ Already Managed")) == 1
    assert large_count == small_count == 1
    assert "COUNT(" not in large_queries[0].upper()
    assert large_queries[0].upper().count("EXISTS(") == 1


def test_discovered_device_admin_urls_and_promote_view_outcomes() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    model_admin.admin_site.admin_view = Mock(side_effect=lambda view: view)
    with patch.object(MicboardModelAdmin, "get_urls", return_value=["base"]):
        assert len(model_admin.get_urls()) == 2
    request = _request("post")
    with (
        patch.object(model_admin, "get_object", return_value=None),
        patch.object(monitoring.messages, "error"),
        patch.object(monitoring, "redirect", return_value=HttpResponse(status=302)),
    ):
        assert model_admin.promote_device_view(request, 1).status_code == 302

    discovered = _discovered()
    with (
        patch.object(model_admin, "get_object", return_value=discovered),
        patch.object(model_admin, "_has_promotion_permission", return_value=False),
        pytest.raises(PermissionDenied),
    ):
        model_admin.promote_device_view(request, 1)

    chassis = SimpleNamespace(pk=8, __str__=lambda self: "Chassis")
    with (
        patch.object(model_admin, "get_object", return_value=discovered),
        patch.object(model_admin, "_has_promotion_permission", return_value=True),
        patch.object(model_admin, "_promote_to_chassis", return_value=(True, "ok", chassis)),
        patch.object(monitoring.messages, "success"),
        patch.object(monitoring, "redirect", return_value=HttpResponse(status=302)) as redirect,
    ):
        model_admin.promote_device_view(request, 1)
    discovered.delete.assert_called_once()
    assert "wirelesschassis/8" in redirect.call_args.args[0]

    with (
        patch.object(model_admin, "get_object", return_value=discovered),
        patch.object(model_admin, "_has_promotion_permission", return_value=True),
        patch.object(model_admin, "_promote_to_chassis", return_value=(False, "failed", None)),
        patch.object(monitoring.messages, "error") as error,
        patch.object(monitoring, "redirect", return_value=HttpResponse(status=302)),
    ):
        model_admin.promote_device_view(request, 1)
    assert "failed" in error.call_args.args[1]


def test_discovered_device_refresh_and_bulk_promotion_actions_report_each_outcome() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    request = _request()
    with (
        patch(
            "micboard.services.sync.device_refresh_service.DeviceRefreshService.refresh_discovered_devices_from_api",
            return_value=(2, 1),
        ),
        patch.object(monitoring.messages, "success") as success,
        patch.object(monitoring.messages, "warning") as warning,
    ):
        model_admin.refresh_from_api(request, MagicMock())
    success.assert_called_once()
    warning.assert_called_once()

    with (
        patch.object(model_admin, "_has_promotion_permission", return_value=False),
        pytest.raises(PermissionDenied),
    ):
        model_admin.promote_to_chassis_action(request, [])
    good = _discovered(ip="192.0.2.1")
    bad = _discovered(ip="192.0.2.2")
    with (
        patch.object(model_admin, "_has_promotion_permission", return_value=True),
        patch.object(
            model_admin,
            "_promote_to_chassis",
            side_effect=[(True, "ok", object()), (False, "failed", None)],
        ),
        patch.object(monitoring.messages, "success") as success,
        patch.object(monitoring.messages, "warning") as warning,
    ):
        model_admin.promote_to_chassis_action(request, [good, bad])
    good.delete.assert_called_once()
    success.assert_called_once()
    warning.assert_called_once()


def test_discovered_device_actions_handle_noop_results_without_false_notifications() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    request = _request()
    with (
        patch(
            "micboard.services.sync.device_refresh_service.DeviceRefreshService.refresh_discovered_devices_from_api",
            return_value=(0, 0),
        ),
        patch.object(monitoring.messages, "success") as success,
        patch.object(monitoring.messages, "warning") as warning,
    ):
        model_admin.refresh_from_api(request, [])
    success.assert_not_called()
    warning.assert_not_called()

    with (
        patch.object(model_admin, "_has_promotion_permission", return_value=True),
        patch.object(monitoring.messages, "success") as success,
        patch.object(monitoring.messages, "warning") as warning,
    ):
        model_admin.promote_to_chassis_action(request, [])
    success.assert_not_called()
    warning.assert_not_called()


def test_discovered_device_delete_delegates_claimed_reconciliation() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    request = _request()
    queryset = MagicMock()
    with (
        patch(
            "micboard.services.sync.discovered_device_deletion_service.DiscoveredDeviceDeletionService.delete",
            return_value=SimpleNamespace(deleted_count=3, scheduled_manufacturers=2),
        ) as delete,
        patch.object(monitoring.messages, "success") as success,
    ):
        model_admin.delete_and_reconcile_discovery(request, queryset)

    delete.assert_called_once_with(queryset)
    assert "Deleted 3" in success.call_args.args[1]
    assert "2 manufacturer" in success.call_args.args[1]


def test_discovered_device_delete_reports_empty_selection() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    request = _request()
    queryset = MagicMock()
    with (
        patch(
            "micboard.services.sync.discovered_device_deletion_service.DiscoveredDeviceDeletionService.delete",
            return_value=SimpleNamespace(deleted_count=0, scheduled_manufacturers=0),
        ),
        patch.object(monitoring.messages, "success") as success,
    ):
        model_admin.delete_and_reconcile_discovery(request, queryset)

    assert "Deleted 0" in success.call_args.args[1]


def test_discovered_device_promotion_service_and_permission_contract() -> None:
    model_admin = _admin(monitoring.DiscoveredDeviceAdmin, DiscoveredDevice)
    discovered = _discovered()
    with patch(
        "micboard.services.sync.device_promotion_service.DevicePromotionService.promote_discovered_device",
        return_value=(True, "ok", object()),
    ) as promote:
        assert model_admin._promote_to_chassis(discovered)[0] is True
    promote.assert_called_once_with(discovered)
    request = _request()
    with (
        patch.object(model_admin, "has_change_permission", return_value=True),
        patch.object(model_admin, "has_delete_permission", return_value=True),
    ):
        assert model_admin._has_promotion_permission(request, discovered) is True
    request.user.has_perm.return_value = False
    with (
        patch.object(model_admin, "has_change_permission", return_value=True),
        patch.object(model_admin, "has_delete_permission", return_value=True),
    ):
        assert model_admin._has_promotion_permission(request) is False
