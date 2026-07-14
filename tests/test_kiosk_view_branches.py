"""Focused access and response coverage for kiosk views."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.views.generic import ListView

from micboard.models.hardware.display_wall import DisplayWall
from micboard.views import assignments
from micboard.views.kiosk import (
    DisplayWallDetailView,
    DisplayWallListView,
    KioskAuthView,
    KioskDataView,
    KioskHealthView,
    WallSectionListView,
)
from tests.view_test_helpers import request


def test_kiosk_auth_get_and_post_cover_success_and_missing_wall() -> None:
    kiosk_request = request()
    wall = MagicMock(id=4)
    queryset = MagicMock()
    queryset.get.return_value = wall
    with (
        patch.object(
            assignments.MonitoringService,
            "get_accessible_display_walls",
            return_value=queryset,
            create=True,
        ),
        patch("micboard.views.kiosk.get_object_or_404", return_value=wall),
        patch(
            "micboard.views.kiosk.ChargerAssignmentService.get_display_wall_data",
            return_value={"wall": {"id": 4}},
        ),
        patch("micboard.views.kiosk.render", return_value=HttpResponse()) as render,
        patch("django.utils.timezone.now", return_value="now"),
    ):
        assert KioskAuthView().get(kiosk_request, "wall-4").status_code == 200
        assert KioskAuthView().post(kiosk_request, "wall-4").status_code == 200
    assert render.call_args.args[2]["sections"] == []
    assert wall.last_heartbeat == "now"
    wall.save.assert_called_once_with(update_fields=["last_heartbeat"])

    queryset.get.side_effect = DisplayWall.DoesNotExist
    with patch(
        "micboard.views.kiosk.MonitoringService.get_accessible_display_walls",
        return_value=queryset,
    ):
        response = KioskAuthView().post(kiosk_request, "missing")
    assert response.status_code == 404


def test_kiosk_list_detail_and_section_views_scope_querysets_and_context() -> None:
    kiosk_request = request()
    queryset = MagicMock()
    with patch(
        "micboard.views.kiosk.MonitoringService.get_accessible_display_walls",
        return_value=queryset,
    ):
        list_view = DisplayWallListView()
        list_view.request = kiosk_request
        assert list_view.get_queryset() is queryset.filter.return_value.order_by.return_value
        with patch.object(ListView, "get_context_data", return_value={"walls": []}):
            assert list_view.get_context_data() == {"walls": []}

        detail = DisplayWallDetailView()
        detail.request = kiosk_request
        assert detail.get_queryset() is queryset.filter.return_value

    sections = MagicMock()
    section_view = WallSectionListView()
    section_view.request = kiosk_request
    section_view.kwargs = {"wall_id": 9}
    with (
        patch(
            "micboard.views.kiosk.MonitoringService.get_accessible_wall_sections",
            return_value=sections,
        ),
        patch(
            "micboard.views.kiosk.MonitoringService.get_accessible_display_walls",
            return_value=queryset,
        ),
        patch("micboard.views.kiosk.get_object_or_404", return_value="wall"),
        patch.object(ListView, "get_context_data", return_value={"sections": []}),
    ):
        assert section_view.get_queryset() is sections.filter.return_value.order_by.return_value
        assert section_view.get_context_data()["wall"] == "wall"


def test_kiosk_data_view_returns_data_and_not_found() -> None:
    kiosk_request = request()
    wall = SimpleNamespace(id=5)
    queryset = MagicMock()
    queryset.get.return_value = wall
    with (
        patch(
            "micboard.views.kiosk.MonitoringService.get_accessible_display_walls",
            return_value=queryset,
        ),
        patch(
            "micboard.views.kiosk.ChargerAssignmentService.get_display_wall_data",
            return_value={"wall": {"id": 5}},
        ),
    ):
        response = KioskDataView().get(kiosk_request, 5)
    assert json.loads(response.content) == {
        "status": "ok",
        "wall": {"id": 5},
        "sections": [],
    }

    queryset.get.side_effect = DisplayWall.DoesNotExist
    with patch(
        "micboard.views.kiosk.MonitoringService.get_accessible_display_walls",
        return_value=queryset,
    ):
        assert KioskDataView().get(kiosk_request, 5).status_code == 404


def test_kiosk_health_view_checks_only_accessible_chargers_and_handles_missing_wall() -> None:
    kiosk_request = request()
    wall = SimpleNamespace(id=5)
    health = [{"id": 1}, {"id": 2}]
    with patch(
        "micboard.views.kiosk.ConnectionValidationService.get_display_wall_charger_health",
        return_value=(wall, health),
    ) as get_health:
        response = KioskHealthView().get(kiosk_request, 5)
    assert json.loads(response.content)["chargers"] == health
    get_health.assert_called_once_with(wall_id=5, user=kiosk_request.user)

    with patch(
        "micboard.views.kiosk.ConnectionValidationService.get_display_wall_charger_health",
        side_effect=DisplayWall.DoesNotExist,
    ):
        assert KioskHealthView().get(kiosk_request, 5).status_code == 404
