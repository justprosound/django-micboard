"""Focused controller coverage for dashboard and charger views."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.views.generic import TemplateView

import pytest

from micboard.views import dashboard
from micboard.views.charger_dashboard import ChargerDashboardView, ChargerGridView
from tests.view_test_helpers import request, view


def test_charger_dashboard_context_uses_one_typed_snapshot_boundary() -> None:
    dashboard_view = ChargerDashboardView()
    dashboard_view.request = request()
    profile = SimpleNamespace(display_width_px=1440)
    snapshot = object()
    with (
        patch.object(TemplateView, "get_context_data", return_value={}),
        patch(
            "micboard.views.charger_dashboard.UserProfile.objects.get_or_create",
            return_value=(profile, True),
        ),
        patch(
            "micboard.views.charger_dashboard.ChargerDashboardService.get_snapshot",
            return_value=snapshot,
        ) as get_snapshot,
    ):
        context = dashboard_view.get_context_data()

    assert context["display_width_px"] == 1440
    assert context["snapshot"] is snapshot
    get_snapshot.assert_called_once_with(user=dashboard_view.request.user)


def test_charger_grid_context_uses_typed_snapshot_without_profile_work() -> None:
    grid_view = ChargerGridView()
    grid_view.request = request()
    snapshot = object()
    with (
        patch.object(TemplateView, "get_context_data", return_value={}),
        patch(
            "micboard.views.charger_dashboard.ChargerDashboardService.get_snapshot",
            return_value=snapshot,
        ) as get_snapshot,
        patch("micboard.views.charger_dashboard.UserProfile.objects.get_or_create") as profile,
    ):
        context = grid_view.get_context_data()

    assert context == {"snapshot": snapshot}
    get_snapshot.assert_called_once_with(user=grid_view.request.user)
    profile.assert_not_called()


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

        with patch.object(
            dashboard_view,
            "get_context_data",
            return_value={},
        ) as get_context:
            assert (
                dashboard_view.post(request("post", data={"display_width_px": "wide"})).status_code
                == 400
            )
        assert get_context.call_args.kwargs["display_width_form"].errors
        render_invalid.assert_called_once_with({}, status=400)
    get.assert_called_once()


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
    ("function", "argument", "expected_criteria"),
    [
        (dashboard.device_type_view, "all", {"role": None}),
        (dashboard.device_type_view, "receiver", {"role": "receiver"}),
        (dashboard.priority_view, "all", {"priority": None}),
        (
            dashboard.priority_view,
            "critical",
            {"priority": "critical"},
        ),
    ],
)
def test_receiver_dashboard_views_translate_routes_to_typed_criteria(
    function: Any, argument: str, expected_criteria: dict[str, Any]
) -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    with (
        patch.object(
            dashboard.ReceiverBrowseService,
            "get_page",
            return_value=MagicMock(),
        ) as get_page,
        patch.object(dashboard, "render", return_value=HttpResponse()),
    ):
        assert view(function)(dashboard_request, argument).status_code == 200
    criteria = get_page.call_args.kwargs["criteria"]
    assert criteria.manufacturer_code == "vendor"
    for field, expected in expected_criteria.items():
        assert getattr(criteria, field) == expected


def test_performer_view_uses_visible_performer_identity() -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    performer = SimpleNamespace(pk=7, name="Alice")
    with (
        patch.object(dashboard.Performer.objects, "for_user", return_value=MagicMock()),
        patch.object(dashboard, "get_object_or_404", return_value=performer),
        patch.object(
            dashboard.ReceiverBrowseService,
            "get_page",
            return_value=MagicMock(),
        ) as get_page,
        patch.object(dashboard, "render", return_value=HttpResponse()),
    ):
        assert view(dashboard.performer_view)(dashboard_request, performer.pk).status_code == 200
    criteria = get_page.call_args.kwargs["criteria"]
    assert criteria.performer_id == performer.pk
    assert criteria.manufacturer_code == "vendor"


@pytest.mark.parametrize(
    ("function", "argument"),
    [(dashboard.device_type_view, "mystery"), (dashboard.priority_view, "urgent")],
)
def test_receiver_dashboard_views_reject_unknown_choice(
    function: Any,
    argument: str,
) -> None:
    with pytest.raises(dashboard.Http404):
        view(function)(request(), argument)


def test_building_room_and_listing_views_use_stable_ids() -> None:
    dashboard_request = request(path="/?manufacturer=vendor")
    buildings = MagicMock()
    rooms = MagicMock()
    building = SimpleNamespace(pk=10, name="Main")
    room = SimpleNamespace(pk=20, name="Studio", building=building, building_id=building.pk)
    rooms.select_related.return_value = rooms

    with (
        patch.object(
            dashboard.MonitoringService, "get_accessible_buildings", return_value=buildings
        ),
        patch.object(dashboard.MonitoringService, "get_accessible_rooms", return_value=rooms),
        patch.object(dashboard, "get_object_or_404", side_effect=[building, room, building]),
        patch.object(dashboard.ReceiverBrowseService, "get_page", return_value=MagicMock()),
        patch.object(dashboard, "render", return_value=HttpResponse()) as render,
    ):
        assert (
            view(dashboard.single_building_view)(dashboard_request, building.pk).status_code == 200
        )
        assert view(dashboard.room_view)(dashboard_request, room.pk).status_code == 200
        assert view(dashboard.all_buildings_view)(dashboard_request).status_code == 200
        assert view(dashboard.all_rooms_view)(dashboard_request).status_code == 200
        assert (
            view(dashboard.rooms_in_building_view)(dashboard_request, building.pk).status_code
            == 200
        )
    assert render.call_count == 5
    buildings.order_by.assert_called_once_with("name")
    assert rooms.select_related.call_count == 2
