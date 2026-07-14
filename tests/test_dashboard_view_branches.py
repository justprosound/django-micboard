"""Focused controller coverage for dashboard and charger views."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.views.generic import ListView

import pytest

from micboard.views import dashboard
from micboard.views.charger_dashboard import ChargerDashboardView
from tests.view_test_helpers import request, view


def test_charger_dashboard_queryset_is_scoped_active_prefetched_and_ordered() -> None:
    dashboard_view = ChargerDashboardView()
    dashboard_view.request = request()
    queryset = MagicMock()
    with patch("micboard.views.charger_dashboard.Charger.objects.for_user", return_value=queryset):
        result = dashboard_view.get_queryset()
    assert (
        result is queryset.filter.return_value.prefetch_related.return_value.order_by.return_value
    )
    queryset.filter.assert_called_once_with(is_active=True)


def test_charger_dashboard_context_maps_assigned_unit_serials() -> None:
    dashboard_view = ChargerDashboardView()
    dashboard_view.request = request()
    profile = SimpleNamespace(display_width_px=1440)
    photo = SimpleNamespace(url="/photo.jpg")
    assignments_list = [
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="A"),
            performer=SimpleNamespace(name="Alice", title="Lead", photo=photo),
        ),
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="B"),
            performer=SimpleNamespace(name="Bob", title=None, photo=None),
        ),
        SimpleNamespace(wireless_unit=None, performer=SimpleNamespace()),
    ]
    queryset = MagicMock()
    queryset.filter.return_value.select_related.return_value = assignments_list
    with (
        patch.object(ListView, "get_context_data", return_value={"chargers": []}),
        patch(
            "micboard.views.charger_dashboard.UserProfile.objects.get_or_create",
            return_value=(profile, True),
        ),
        patch(
            "micboard.views.charger_dashboard.PerformerAssignment.objects.for_user",
            return_value=queryset,
        ),
    ):
        context = dashboard_view.get_context_data()

    assert context["display_width_px"] == 1440
    assert context["serial_to_performer"] == {
        "A": {"name": "Alice", "title": "Lead", "photo_url": "/photo.jpg"},
        "B": {"name": "Bob", "title": "", "photo_url": None},
    }


def test_charger_dashboard_get_switches_only_htmx_template() -> None:
    dashboard_view = ChargerDashboardView()
    with patch.object(ListView, "get", return_value=HttpResponse()) as get:
        dashboard_view.get(request())
        assert dashboard_view.template_name == "micboard/charger_dashboard.html"
        hx_request = request()
        hx_request.headers = {"HX-Request": "true"}
        dashboard_view.get(hx_request)
    assert dashboard_view.template_name == "micboard/partials/charger_grid.html"
    assert get.call_count == 2


def test_charger_dashboard_post_updates_width_and_supports_htmx() -> None:
    dashboard_view = ChargerDashboardView()
    post_request = request("post", data={"display_width_px": "1200"})
    with (
        patch.object(dashboard_view, "get", return_value=HttpResponse("grid")) as get,
        patch.object(
            dashboard_view,
            "render_to_response",
            return_value=HttpResponse(status=400),
        ) as render_invalid,
        patch("micboard.views.charger_dashboard.UserProfileService.set_display_width") as set_width,
        patch("micboard.views.charger_dashboard.redirect", return_value=HttpResponse(status=302)),
    ):
        assert dashboard_view.post(post_request).status_code == 302
        set_width.assert_called_once_with(user=post_request.user, width_px=1200)

        hx_request = request("post", data={"display_width_px": "1920"})
        hx_request.headers = {"HX-Request": "true"}
        assert dashboard_view.post(hx_request).content == b"grid"

        with (
            patch.object(dashboard_view, "get_queryset", return_value=[]) as get_queryset,
            patch.object(dashboard_view, "get_context_data", return_value={}) as get_context,
        ):
            assert (
                dashboard_view.post(request("post", data={"display_width_px": "wide"})).status_code
                == 400
            )
        get_queryset.assert_called_once_with()
        assert get_context.call_args.kwargs["display_width_form"].errors
        render_invalid.assert_called_once_with({}, status=400)
    get.assert_called_once()


def test_get_filtered_receivers_covers_filter_backend_and_manufacturer_paths() -> None:
    dashboard_request = request(path="/?search=desk")
    queryset = MagicMock()
    filtered = MagicMock()
    with (
        patch.object(dashboard.WirelessChassis.objects, "for_user", return_value=queryset),
        patch.object(dashboard, "HAS_DJANGO_FILTERS", True),
        patch.object(dashboard, "WirelessChassisFilter") as filter_class,
    ):
        filter_class.return_value.qs = filtered
        result = dashboard.get_filtered_receivers(
            dashboard_request, "vendor", location__name="Stage"
        )
    queryset.filter.assert_called_once_with(location__name="Stage")
    filtered.by_manufacturer.assert_called_once_with(manufacturer="vendor")
    assert result is filtered.by_manufacturer.return_value.distinct.return_value

    fallback = MagicMock(spec=["filter", "distinct"])
    fallback.filter.return_value = fallback
    with (
        patch.object(dashboard.WirelessChassis.objects, "for_user", return_value=fallback),
        patch.object(dashboard, "HAS_DJANGO_FILTERS", False),
    ):
        result = dashboard.get_filtered_receivers(dashboard_request, "vendor", is_online=True)
    fallback.filter.assert_any_call(is_online=True)
    fallback.filter.assert_any_call(manufacturer__code="vendor")
    assert result is fallback.distinct.return_value

    no_vendor = MagicMock()
    no_vendor.filter.return_value = no_vendor
    with (
        patch.object(dashboard.WirelessChassis.objects, "for_user", return_value=no_vendor),
        patch.object(dashboard, "HAS_DJANGO_FILTERS", False),
    ):
        dashboard.get_filtered_receivers(dashboard_request, None)
    no_vendor.distinct.assert_called_once_with()


def test_simple_dashboard_pages_build_expected_contexts() -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    receivers = MagicMock()
    groups = MagicMock()
    with (
        patch.object(dashboard.WirelessChassis.objects, "for_user", return_value=receivers),
        patch.object(
            dashboard.MonitoringService, "get_user_monitoring_groups", return_value=groups
        ),
        patch.object(dashboard, "render", return_value=HttpResponse()) as render,
    ):
        view(dashboard.index)(dashboard_request)
        view(dashboard.about)(dashboard_request)
    assert render.call_args_list[0].args[2] == {
        "device_count": receivers.count.return_value,
        "group_count": groups.count.return_value,
    }
    assert render.call_args_list[1].args[1] == "micboard/about.html"


@pytest.mark.parametrize(
    ("function", "argument", "expected_filters"),
    [
        (dashboard.device_type_view, "all", {"is_online": True}),
        (dashboard.device_type_view, "receiver", {"role": "receiver", "is_online": True}),
        (dashboard.priority_view, "all", {"is_online": True}),
        (
            dashboard.priority_view,
            "urgent",
            {"field_units__performer_assignments__priority": "urgent", "is_online": True},
        ),
        (
            dashboard.user_view,
            "Alice",
            {
                "field_units__performer_assignments__performer__name": "Alice",
                "is_online": True,
            },
        ),
    ],
)
def test_receiver_dashboard_views_translate_routes_to_filters(
    function: Any, argument: str, expected_filters: dict[str, Any]
) -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    with (
        patch.object(dashboard, "get_filtered_receivers", return_value="receivers") as filtered,
        patch.object(dashboard, "render", return_value=HttpResponse()),
    ):
        assert view(function)(dashboard_request, argument).status_code == 200
    filtered.assert_called_once_with(dashboard_request, "vendor", **expected_filters)


def test_building_room_and_listing_views_cover_all_route_variants() -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    buildings = MagicMock()
    rooms = MagicMock()
    building = object()
    room = object()
    with (
        patch.object(
            dashboard.MonitoringService, "get_accessible_buildings", return_value=buildings
        ),
        patch.object(dashboard, "get_object_or_404", return_value=building),
        patch.object(dashboard, "all_buildings_view", return_value=HttpResponse("all buildings")),
        patch.object(dashboard, "all_rooms_view", return_value=HttpResponse("all rooms")),
        patch.object(
            dashboard, "rooms_in_building_view", return_value=HttpResponse("building rooms")
        ),
    ):
        assert (
            view(dashboard.single_building_view)(dashboard_request, "all").content
            == b"all buildings"
        )
        assert view(dashboard.room_view)(dashboard_request, "all", "all").content == b"all rooms"
        assert (
            view(dashboard.room_view)(dashboard_request, "all", "Room").content == b"all buildings"
        )
        assert (
            view(dashboard.room_view)(dashboard_request, "Main", "all").content == b"building rooms"
        )

    with (
        patch.object(
            dashboard.MonitoringService, "get_accessible_buildings", return_value=buildings
        ),
        patch.object(dashboard.MonitoringService, "get_accessible_rooms", return_value=rooms),
        patch.object(
            dashboard, "get_object_or_404", side_effect=[building, building, room, building]
        ),
        patch.object(dashboard, "get_filtered_receivers", return_value="receivers"),
        patch.object(dashboard, "render", return_value=HttpResponse()) as render,
    ):
        assert view(dashboard.single_building_view)(dashboard_request, "Main").status_code == 200
        assert view(dashboard.room_view)(dashboard_request, "Main", "Room").status_code == 200
        assert view(dashboard.all_buildings_view)(dashboard_request).status_code == 200
        assert view(dashboard.all_rooms_view)(dashboard_request).status_code == 200
        assert view(dashboard.rooms_in_building_view)(dashboard_request, "Main").status_code == 200
    assert render.call_count == 5
    buildings.order_by.assert_called_once_with("name")
    rooms.select_related.assert_called_once_with("building")
