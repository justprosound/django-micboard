"""Focused access, filtering, and mutation coverage for alert views."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.http import Http404, HttpResponse

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.views import alerts
from tests.view_test_helpers import request, view


def test_alert_controller_remaining_filter_and_error_paths() -> None:
    alert_request = request(path="/?status=all")
    with (
        patch.object(alerts.AlertBrowseService, "get_page", return_value=MagicMock()),
        patch.object(alerts.AlertBrowseService, "get_stats", return_value=MagicMock()),
        patch.object(alerts, "render", return_value=HttpResponse()),
    ):
        assert view(alerts.alerts_view)(alert_request).status_code == 200

    with (
        patch.object(alerts, "resolve_alert", side_effect=Alert.DoesNotExist),
        pytest.raises(Http404),
    ):
        view(alerts.resolve_alert_view)(request("post"), 99)

    with (
        patch.object(alerts, "resolve_alert", side_effect=ValueError("already resolved")),
        patch.object(alerts.messages, "error") as error,
        patch.object(alerts, "redirect", return_value=HttpResponse(status=302)),
    ):
        assert view(alerts.resolve_alert_view)(request("post"), 1).status_code == 302
    error.assert_called_once()


def test_alert_list_filters_and_detail_use_user_visible_queryset() -> None:
    alert_request = request(path="/?status=acknowledged&type=battery_low&page=2")
    queryset = MagicMock()
    page = MagicMock()
    stats = MagicMock()
    with (
        patch.object(alerts, "get_alerts_for_user", return_value=queryset),
        patch.object(alerts.AlertBrowseService, "get_page", return_value=page) as get_page,
        patch.object(alerts.AlertBrowseService, "get_stats", return_value=stats),
        patch.object(alerts, "render", return_value=HttpResponse()) as render,
        patch.object(alerts, "get_object_or_404", return_value="alert") as get_object,
    ):
        assert view(alerts.alerts_view)(alert_request).status_code == 200
        assert view(alerts.alert_detail_view)(alert_request, 4).status_code == 200

    criteria = get_page.call_args.kwargs["criteria"]
    assert criteria.status == "acknowledged"
    assert criteria.alert_type == "battery_low"
    assert criteria.page == "2"
    assert render.call_args_list[0].args[2]["browse"] is page
    get_object.assert_called_once()


@pytest.mark.parametrize(
    ("operation", "error", "status"),
    [
        ("acknowledge", None, 302),
        ("acknowledge", ValueError("invalid"), 302),
        ("acknowledge", Alert.DoesNotExist(), 404),
        ("resolve", None, 302),
    ],
)
def test_alert_mutations_cover_success_validation_and_missing_rows(
    operation: str, error: Exception | None, status: int
) -> None:
    service = alerts.acknowledge_alert if operation == "acknowledge" else alerts.resolve_alert
    controller = (
        alerts.acknowledge_alert_view if operation == "acknowledge" else alerts.resolve_alert_view
    )
    service_patch = patch.object(alerts, service.__name__, side_effect=error)
    with (
        service_patch,
        patch.object(alerts.messages, "success") as success,
        patch.object(alerts.messages, "error") as message_error,
        patch.object(alerts, "redirect", return_value=HttpResponse(status=302)),
    ):
        if status == 404:
            with pytest.raises(Http404):
                view(controller)(request("post"), 8)
            return
        response = view(controller)(request("post"), 8)

    assert response.status_code == status
    if error is None:
        success.assert_called_once()
        message_error.assert_not_called()
    else:
        success.assert_not_called()
        message_error.assert_called_once()
