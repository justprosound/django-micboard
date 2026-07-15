"""Focused access and response coverage for kiosk views."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.http import Http404, HttpResponse
from django.views.generic import ListView

import pytest

from micboard.services.kiosk.dtos import (
    DisplayWallHealthSnapshot,
    DisplayWallMetadata,
    DisplayWallSnapshot,
    KioskChargerGroupSnapshot,
    KioskChargerSnapshot,
    WallSectionSnapshot,
)
from micboard.views.kiosk import (
    DisplayWallDetailView,
    DisplayWallListView,
    KioskAuthView,
    KioskContentView,
    KioskDataView,
    KioskHealthView,
    WallSectionListView,
)
from tests.view_test_helpers import request


def _snapshot() -> DisplayWallSnapshot:
    return DisplayWallSnapshot(
        wall=DisplayWallMetadata(
            id=5,
            name="Stage",
            kiosk_id="stage",
            display_width_px=1920,
            display_height_px=1080,
            orientation="landscape",
            refresh_interval_seconds=10,
            show_performer_photos=True,
            show_rf_levels=True,
            show_battery_levels=True,
            show_audio_levels=True,
        ),
        sections=[],
    )


def test_kiosk_auth_get_and_post_cover_success_and_missing_wall() -> None:
    kiosk_request = request()
    snapshot = _snapshot()
    with (
        patch(
            "micboard.views.kiosk.KioskService.get_kiosk_snapshot",
            return_value=snapshot,
        ),
        patch(
            "micboard.views.kiosk.KioskService.record_heartbeat",
            side_effect=[True, False],
        ),
        patch("micboard.views.kiosk.render", return_value=HttpResponse()) as render,
    ):
        assert KioskAuthView().get(kiosk_request, "stage").status_code == 200
        assert KioskAuthView().post(kiosk_request, "stage").status_code == 200
        assert KioskAuthView().post(kiosk_request, "missing").status_code == 404
    assert render.call_args.args[2] == {"snapshot": snapshot, "kiosk": True}

    with (
        patch("micboard.views.kiosk.KioskService.get_kiosk_snapshot", return_value=None),
        pytest.raises(Http404),
    ):
        KioskAuthView().get(kiosk_request, "missing")


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
    snapshot = _snapshot().model_copy(
        update={
            "sections": [
                WallSectionSnapshot(
                    id=7,
                    name="Main",
                    layout="grid",
                    columns=3,
                    performers=[
                        KioskChargerGroupSnapshot(
                            charger=KioskChargerSnapshot(id=8, name="Rack", location_id=9),
                            performers=[],
                        )
                    ],
                )
            ]
        }
    )
    with patch("micboard.views.kiosk.KioskService.get_wall_snapshot", return_value=snapshot):
        response = KioskDataView().get(kiosk_request, 5)
    assert json.loads(response.content) == {
        "status": "ok",
        "wall": snapshot.wall.model_dump(mode="json"),
        "sections": [
            {
                "section": {
                    "id": 7,
                    "name": "Main",
                    "layout": "grid",
                    "columns": 3,
                    "chargers_truncated": False,
                    "charger_limit": 32,
                    "occupied_slots_truncated": False,
                    "occupied_slot_limit": 32,
                },
                "performers": [
                    {
                        "charger": {"id": 8, "name": "Rack", "location_id": 9},
                        "performers": [],
                        "occupied_slots_truncated": False,
                        "occupied_slot_limit": 32,
                    }
                ],
            }
        ],
    }

    with patch("micboard.views.kiosk.KioskService.get_wall_snapshot", return_value=None):
        assert KioskDataView().get(kiosk_request, 5).status_code == 404


def test_kiosk_content_view_renders_html_snapshot_and_not_found() -> None:
    kiosk_request = request()
    snapshot = _snapshot()
    with (
        patch("micboard.views.kiosk.KioskService.get_wall_snapshot", return_value=snapshot),
        patch("micboard.views.kiosk.render", return_value=HttpResponse()) as render,
    ):
        assert KioskContentView().get(kiosk_request, 5).status_code == 200
    assert render.call_args.args[1] == "micboard/kiosk/display_content.html"
    assert render.call_args.args[2] == {"snapshot": snapshot}

    with (
        patch("micboard.views.kiosk.KioskService.get_wall_snapshot", return_value=None),
        pytest.raises(Http404),
    ):
        KioskContentView().get(kiosk_request, 5)


def test_kiosk_health_view_checks_only_accessible_chargers_and_handles_missing_wall() -> None:
    kiosk_request = request()
    health = DisplayWallHealthSnapshot(wall_id=5, chargers=[])
    with patch(
        "micboard.views.kiosk.KioskHealthService.get_wall_health",
        return_value=health,
    ) as get_health:
        response = KioskHealthView().get(kiosk_request, 5)
    assert json.loads(response.content) == {"status": "ok", **health.model_dump(mode="json")}
    get_health.assert_called_once_with(wall_id=5, user=kiosk_request.user)

    with patch(
        "micboard.views.kiosk.KioskHealthService.get_wall_health",
        return_value=None,
    ):
        assert KioskHealthView().get(kiosk_request, 5).status_code == 404
