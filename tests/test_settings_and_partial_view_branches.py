"""Focused controller coverage for partial, settings, and user views."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.http import HttpResponse

import pytest

from micboard.views import partials
from micboard.views import settings as settings_views
from tests.view_test_helpers import request, view


def test_all_partial_views_resolve_scoped_objects_and_service_data() -> None:
    partial_request = request()
    scoped = MagicMock()
    obj = SimpleNamespace(id=4)
    with (
        patch.object(partials, "get_object_or_404", return_value=obj) as get_object,
        patch.object(partials, "render", return_value=HttpResponse()) as render,
        patch(
            "micboard.services.monitoring.monitoring_access.MonitoringService.get_accessible_channels",
            return_value=scoped,
        ),
        patch(
            "micboard.services.monitoring.monitoring_access.MonitoringService.get_accessible_charger_slots",
            return_value=scoped,
        ),
        patch(
            "micboard.services.monitoring.monitoring_access.MonitoringService.get_accessible_wall_sections",
            return_value=scoped,
        ),
        patch("micboard.services.kiosk.KioskService.get_section_data", return_value={"x": 1}),
        patch.object(partials, "get_alerts_for_user", return_value=scoped),
        patch.object(partials.PerformerAssignment.objects, "for_user", return_value=scoped),
        patch("micboard.services.kiosk.KioskService.get_charger_dashboard_data", return_value={}),
        patch.object(partials.WirelessChassis.objects, "for_user", return_value=scoped),
    ):
        for function, args in (
            (partials.channel_card_partial, (4,)),
            (partials.charger_slot_partial, (4,)),
            (partials.wall_section_partial, (4,)),
            (partials.alert_row_partial, (4,)),
            (partials.assignment_row_partial, (4,)),
            (partials.charger_grid_partial, ()),
            (partials.device_tiles_partial, ()),
        ):
            assert view(function)(partial_request, *args).status_code == 200
    assert get_object.call_count == 5
    assert render.call_count == 7


def _configure_form_view(form_view: Any) -> Any:
    form_view.request = request()
    form_view.success_url = "/admin/settings/"
    return form_view


@pytest.mark.parametrize(
    "view_class", [settings_views.BulkSettingConfigView, settings_views.ManufacturerSettingsView]
)
def test_settings_form_views_bind_user_and_add_page_context(view_class: type) -> None:
    form_view = _configure_form_view(view_class())
    with (
        patch("django.views.generic.edit.FormMixin.get_form_kwargs", return_value={"data": None}),
        patch("django.views.generic.edit.FormMixin.get_context_data", return_value={}),
    ):
        kwargs = form_view.get_form_kwargs()
        context = form_view.get_context_data()
    assert kwargs["user"] is form_view.request.user
    assert context["title"].startswith("Configure")
    assert context["description"]


def test_bulk_settings_form_valid_reports_success_errors_and_redirects() -> None:
    form_view = _configure_form_view(settings_views.BulkSettingConfigView())
    form = MagicMock()
    form.save_settings.return_value = {"saved": 2, "errors": ["one", "two"]}
    with (
        patch.object(settings_views.messages, "success") as success,
        patch.object(settings_views.messages, "error") as error,
        patch.object(settings_views, "redirect", return_value=HttpResponse(status=302)),
    ):
        response = form_view.form_valid(form)
    assert response.status_code == 302
    success.assert_called_once()
    assert error.call_count == 2


def test_bulk_settings_form_valid_handles_no_messages_and_failure() -> None:
    form_view = _configure_form_view(settings_views.BulkSettingConfigView())
    form = MagicMock()
    form.save_settings.return_value = {"saved": 0, "errors": []}
    with (
        patch.object(settings_views.messages, "success") as success,
        patch.object(settings_views.messages, "error") as error,
        patch.object(settings_views, "redirect", return_value=HttpResponse(status=302)),
    ):
        form_view.form_valid(form)
    success.assert_not_called()
    error.assert_not_called()

    form.save_settings.side_effect = RuntimeError("db")
    with (
        patch.object(settings_views.messages, "error") as error,
        patch.object(form_view, "form_invalid", return_value=HttpResponse(status=400)) as invalid,
    ):
        assert form_view.form_valid(form).status_code == 400
    error.assert_called_once()
    invalid.assert_called_once_with(form)


def test_manufacturer_settings_initial_covers_present_and_absent_query_value() -> None:
    form_view = _configure_form_view(settings_views.ManufacturerSettingsView())
    with patch("django.views.generic.edit.FormMixin.get_initial", return_value={}):
        assert form_view.get_initial() == {}
        form_view.request = request(path="/?manufacturer=12")
        assert form_view.get_initial() == {"manufacturer": "12"}


def test_manufacturer_settings_form_valid_reports_and_handles_failure() -> None:
    form_view = _configure_form_view(settings_views.ManufacturerSettingsView())
    form = MagicMock()
    form.cleaned_data = {"manufacturer": SimpleNamespace(name="Vendor")}
    form.save_settings.return_value = {"saved": 1, "errors": ["bad value"]}
    with (
        patch.object(settings_views.messages, "success") as success,
        patch.object(settings_views.messages, "error") as error,
        patch.object(settings_views, "redirect", return_value=HttpResponse(status=302)),
    ):
        assert form_view.form_valid(form).status_code == 302
    success.assert_called_once()
    error.assert_called_once()

    form.save_settings.side_effect = RuntimeError("db")
    with (
        patch.object(settings_views.messages, "error") as error,
        patch.object(form_view, "form_invalid", return_value=HttpResponse(status=400)),
    ):
        assert form_view.form_valid(form).status_code == 400
    error.assert_called_once()


def test_manufacturer_settings_form_valid_handles_empty_result_without_messages() -> None:
    form_view = _configure_form_view(settings_views.ManufacturerSettingsView())
    form = MagicMock()
    form.cleaned_data = {"manufacturer": SimpleNamespace(name="Vendor")}
    form.save_settings.return_value = {"saved": 0, "errors": []}
    with (
        patch.object(settings_views.messages, "success") as success,
        patch.object(settings_views.messages, "error") as error,
        patch.object(settings_views, "redirect", return_value=HttpResponse(status=302)),
    ):
        assert form_view.form_valid(form).status_code == 302
    success.assert_not_called()
    error.assert_not_called()


def test_settings_function_views_delegate_presentation_context() -> None:
    settings_request = request()
    with (
        patch.object(settings_views.settings_presentation, "get_diff", return_value={"diff": 1}),
        patch.object(
            settings_views.settings_presentation, "get_overview", return_value={"overview": 1}
        ),
        patch.object(settings_views, "render", return_value=HttpResponse()) as render,
    ):
        view(settings_views.settings_diff_view)(settings_request)
        view(settings_views.settings_overview)(settings_request)
    assert render.call_args_list[0].args[2] == {"diff": 1}
    assert render.call_args_list[1].args[2] == {"overview": 1}
