"""Coverage for integration and real-time connection admin behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from micboard.admin import (
    integrations,
    realtime,
)
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.integrations import Accessory, ManufacturerAPIServer
from micboard.models.realtime.connection import RealTimeConnection

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _request() -> Any:
    request = RequestFactory().get("/admin/")
    request.user = SimpleNamespace(pk=4, is_authenticated=True, is_superuser=True)
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_api_server_admin_secure_details_displays_and_actions() -> None:
    model_admin = _admin(integrations.ManufacturerAPIServerAdmin, ManufacturerAPIServer)
    request = _request()
    obj = SimpleNamespace(
        shared_key="secret",
        status=ManufacturerAPIServer.Status.ACTIVE,
        get_status_display=lambda: "Active",
        location_name="Stage",
        get_manufacturer_display=lambda: "Vendor",
        last_health_check=NOW,
        enabled=True,
    )
    with (
        patch.object(model_admin, "has_change_permission", return_value=False),
        patch.object(integrations, "replace_field", return_value=[("safe", {})]),
    ):
        assert model_admin.get_fieldsets(request, obj) == [("safe", {})]
    with patch.object(MicboardModelAdmin, "get_fieldsets", return_value=[("base", {})]):
        assert model_admin.get_fieldsets(request, None) == [("base", {})]
    assert model_admin.shared_key_masked(obj) == "••••••"
    assert "Active" in model_admin.status_indicator(obj)
    assert model_admin.manufacturer_with_location(obj) == "Vendor (Stage)"
    assert model_admin.health_check_status(obj) == "2026-07-14 12:00"
    assert model_admin.enabled_badge(obj) is True
    obj.shared_key = ""
    obj.location_name = ""
    obj.last_health_check = None
    obj.status = "custom"
    assert model_admin.shared_key_masked(obj) == "Not configured"
    assert "No location" in model_admin.manufacturer_with_location(obj)
    assert model_admin.health_check_status(obj) == "Never tested"

    queryset = MagicMock()
    queryset.update.side_effect = [2, 1]
    model_admin.message_user = Mock()
    model_admin.enable_servers(request, queryset)
    model_admin.disable_servers(request, queryset)
    assert model_admin.has_import_permission(request) is False
    assert model_admin.has_export_permission(request) is False


def test_api_server_admin_queues_exact_selection_without_vendor_io() -> None:
    """The request only submits selected identifiers to a permission-checked worker."""
    model_admin = _admin(integrations.ManufacturerAPIServerAdmin, ManufacturerAPIServer)
    request = _request()
    queryset = MagicMock()
    queryset.db = "inventory"
    queryset.order_by.return_value.values_list.return_value.__getitem__.return_value = [7, 9]
    model_admin.message_user = Mock()

    with (
        patch.object(integrations, "huey_is_configured", return_value=True),
        patch.object(integrations, "enqueue_huey_task") as enqueue,
    ):
        model_admin.test_connection(request, queryset)

    enqueue.assert_called_once_with(
        integrations.check_selected_api_server_connections,
        [7, 9],
        request.user.pk,
        using="inventory",
    )
    assert "Queued health checks for 2" in model_admin.message_user.call_args.args[1]


def test_api_server_admin_rejects_unbounded_or_unavailable_batches() -> None:
    """Oversized selections and missing workers fail closed without external I/O."""
    model_admin = _admin(integrations.ManufacturerAPIServerAdmin, ManufacturerAPIServer)
    request = _request()
    queryset = MagicMock()
    queryset.db = "default"
    selected = list(range(integrations.MAX_API_SERVER_HEALTH_CHECK_BATCH + 1))
    queryset.order_by.return_value.values_list.return_value.__getitem__.return_value = selected
    model_admin.message_user = Mock()

    with patch.object(integrations, "enqueue_huey_task") as enqueue:
        model_admin.test_connection(request, queryset)
    enqueue.assert_not_called()
    assert "Select at most" in model_admin.message_user.call_args.args[1]

    queryset.order_by.return_value.values_list.return_value.__getitem__.return_value = [7]
    with (
        patch.object(integrations, "huey_is_configured", return_value=False),
        patch.object(integrations, "enqueue_huey_task") as enqueue,
    ):
        model_admin.test_connection(request, queryset)
    enqueue.assert_not_called()
    assert "configured Huey worker" in model_admin.message_user.call_args.args[1]


def test_accessory_admin_displays_links_and_bulk_actions() -> None:
    model_admin = _admin(integrations.AccessoryAdmin, Accessory)
    obj = SimpleNamespace(
        get_category_display=lambda: "Antenna",
        chassis=SimpleNamespace(id=3, __str__=lambda self: "Receiver"),
        is_available=True,
        get_condition_display=lambda: "Good",
    )
    with patch.object(integrations, "reverse", return_value="/chassis/3/"):
        assert model_admin.category_badge(obj) == "Antenna"
        assert "/chassis/3/" in model_admin.chassis_link(obj)
    assert model_admin.availability_status(obj) is True
    assert model_admin.condition_badge(obj) == "Good"
    queryset = MagicMock()
    queryset.update.side_effect = [3, 2, 1]
    model_admin.message_user = Mock()
    model_admin.mark_available(_request(), queryset)
    model_admin.mark_unavailable(_request(), queryset)
    model_admin.mark_needs_repair(_request(), queryset)
    model_admin.update_checkout_status(_request(), queryset)
    assert queryset.update.call_args_list == [
        call(is_available=True),
        call(is_available=False),
        call(condition="needs_repair", is_available=False),
    ]
    assert model_admin.message_user.call_count == 4


def test_realtime_admin_displays_duration_actions_and_optimized_queryset() -> None:
    model_admin = _admin(realtime.RealTimeConnectionAdmin, RealTimeConnection)
    obj = SimpleNamespace(status="connected", get_status_display=lambda: "Connected")
    assert "Connected" in model_admin.status_colored(obj)
    obj.status = "custom"
    assert "Connected" in model_admin.status_colored(obj)
    with (
        patch.object(realtime, "connection_duration", return_value=timedelta(seconds=3661)),
        patch.object(realtime, "time_since_last_message", return_value=timedelta(seconds=62)),
    ):
        assert model_admin.connection_duration(obj) == "01:01:01"
        assert model_admin.time_since_last_message(obj) == "00:01:02"
    with (
        patch.object(realtime, "connection_duration", return_value=None),
        patch.object(realtime, "time_since_last_message", return_value=None),
    ):
        assert model_admin.connection_duration(obj) == "-"
        assert model_admin.time_since_last_message(obj) == "-"
    queryset = MagicMock()
    queryset.update.return_value = 2
    model_admin.message_user = Mock()
    with patch.object(realtime.timezone, "now", return_value=NOW):
        model_admin.mark_connected(_request(), queryset)
        model_admin.mark_disconnected(_request(), queryset)
        model_admin.reset_error_count(_request(), queryset)
        model_admin.stop_connections(_request(), queryset)
    assert queryset.update.call_count == 4
    with patch.object(MicboardModelAdmin, "get_queryset", return_value=queryset):
        assert model_admin.get_queryset(_request()) is queryset.select_related.return_value
