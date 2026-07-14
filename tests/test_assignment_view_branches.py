"""Focused controller coverage for performer assignment views."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse

import pytest

from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from micboard.views import assignments
from tests.view_test_helpers import request, view


def test_assignment_form_context_covers_defaults_existing_values_and_error() -> None:
    with (
        patch.object(assignments.Performer.objects, "for_user", return_value="performers"),
        patch.object(assignments.WirelessUnit.objects, "for_user", return_value="units"),
        patch.object(
            assignments.MonitoringService, "get_user_monitoring_groups", return_value="groups"
        ),
    ):
        default = assignments._assignment_form_context(user="user")
        current = SimpleNamespace(
            priority="high",
            alert_on_battery_low=False,
            alert_on_signal_loss=True,
            alert_on_audio_low=True,
            alert_on_hardware_offline=False,
        )
        populated = assignments._assignment_form_context(
            user="user", assignment=current, error="invalid"
        )

    assert default["selected_priority"] == "normal"
    assert [option["checked"] for option in default["alert_options"]] == [True, True, False, True]
    assert populated["selected_priority"] == "high"
    assert populated["error"] == "invalid"
    assert [option["checked"] for option in populated["alert_options"]] == [
        False,
        True,
        True,
        False,
    ]


def test_assignment_list_queryset_is_user_scoped_and_eager_loaded() -> None:
    assignment_view = assignments.AssignmentListView()
    assignment_view.request = request()
    queryset = MagicMock()
    with patch.object(
        assignments.PerformerAssignmentService,
        "get_visible_assignments",
        return_value=queryset,
    ) as get_visible:
        assert assignment_view.get_queryset() is queryset
    get_visible.assert_called_once_with(user=assignment_view.request.user)


def test_assignment_rows_view_uses_count_free_service_projection() -> None:
    assert assignments.AssignmentRowsView.template_name == "micboard/partials/assignment_rows.html"
    assert assignments.AssignmentListView.paginate_by == 50
    assert assignments.AssignmentRowsView.paginate_by is None

    assignment_view = assignments.AssignmentRowsView()
    assignment_view.request = request(path="/?page=2")
    queryset = MagicMock()
    with patch.object(
        assignments.PerformerAssignmentService,
        "get_visible_assignment_rows",
        return_value=queryset,
    ) as get_rows:
        assert assignment_view.get_queryset() is queryset
    get_rows.assert_called_once_with(user=assignment_view.request.user, page="2")


def test_create_assignment_get_and_missing_fields_render_scoped_form() -> None:
    with (
        patch.object(
            assignments, "_assignment_form_context", return_value={"form": "context"}
        ) as context,
        patch.object(
            assignments,
            "render",
            side_effect=lambda *_args, **kwargs: HttpResponse(status=kwargs.get("status", 200)),
        ) as render,
    ):
        get_request = request()
        assert view(assignments.create_assignment)(get_request).status_code == 200
        missing_request = request("post", data={"performer_id": "1"})
        assert view(assignments.create_assignment)(missing_request).status_code == 400

    assert render.call_count == 2
    assert context.call_args_list[0] == call(user=get_request.user)
    assert context.call_args_list[1].kwargs["error"] == assignments.ASSIGNMENT_FORM_ERROR
    assert context.call_args_list[1].kwargs["form"].errors


def _valid_assignment_request() -> Any:
    return request(
        "post",
        data={
            "performer_id": "1",
            "wireless_unit_id": "2",
            "monitoring_group_id": "3",
            "priority": "high",
            "notes": "notes",
            "alert_on_battery_low": "on",
            "alert_on_audio_low": "on",
        },
    )


def test_create_assignment_delegates_all_values_and_redirects() -> None:
    assignment_request = _valid_assignment_request()
    with (
        patch.object(assignments.PerformerAssignmentService, "create_assignment") as create,
        patch.object(assignments, "redirect", return_value=HttpResponse(status=302)) as redirect,
    ):
        response = view(assignments.create_assignment)(assignment_request)

    assert response.status_code == 302
    create.assert_called_once_with(
        command=CreatePerformerAssignment(
            performer_id=1,
            unit_id=2,
            group_id=3,
            priority="high",
            notes="notes",
            alert_on_battery_low=True,
            alert_on_signal_loss=None,
            alert_on_audio_low=True,
            alert_on_hardware_offline=None,
        ),
        user=assignment_request.user,
    )
    redirect.assert_called_once_with("micboard:assignments")


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (PermissionDenied(), 403),
        (ValidationError("invalid"), 400),
        (RuntimeError("broken"), 500),
    ],
)
def test_create_assignment_maps_service_failures(error: Exception, expected_status: int) -> None:
    assignment_request = _valid_assignment_request()
    with (
        patch.object(
            assignments.PerformerAssignmentService, "create_assignment", side_effect=error
        ),
        patch.object(assignments, "_assignment_form_context", return_value={}) as context,
        patch.object(
            assignments,
            "render",
            side_effect=lambda *_args, **kwargs: HttpResponse(status=kwargs.get("status", 200)),
        ) as render,
    ):
        response = view(assignments.create_assignment)(assignment_request)

    assert response.status_code == expected_status
    if expected_status in {400, 500}:
        render.assert_called_once()
        error_message = context.call_args.kwargs["error"]
        expected_message = (
            assignments.ASSIGNMENT_FORM_ERROR
            if expected_status == 400
            else assignments.ASSIGNMENT_SAVE_ERROR
        )
        assert error_message == expected_message
        assert str(error) not in error_message


def _assignment() -> Any:
    return SimpleNamespace(
        id=9,
        pk=9,
        priority="normal",
        notes="old",
        alert_on_battery_low=True,
        alert_on_signal_loss=True,
        alert_on_audio_low=False,
        alert_on_hardware_offline=True,
    )


def test_update_assignment_get_renders_existing_assignment() -> None:
    assignment = _assignment()
    with (
        patch.object(assignments.PerformerAssignment.objects, "for_user", return_value="visible"),
        patch.object(assignments, "get_object_or_404", return_value=assignment),
        patch.object(assignments, "_assignment_form_context", return_value={}) as context,
        patch.object(assignments, "render", return_value=HttpResponse()),
    ):
        response = view(assignments.update_assignment)(request(), pk=9)
    assert response.status_code == 200
    assert context.call_args.kwargs["assignment"] is assignment


def test_update_assignment_delegates_post_values() -> None:
    assignment = _assignment()
    assignment_request = request(
        "post",
        data={
            "priority": "critical",
            "notes": "new",
            "is_active": "on",
            "alert_on_signal_loss": "on",
        },
    )
    with (
        patch.object(assignments.PerformerAssignment.objects, "for_user", return_value="visible"),
        patch.object(assignments, "get_object_or_404", return_value=assignment),
        patch.object(assignments.PerformerAssignmentService, "update_assignment") as update,
        patch.object(assignments, "redirect", return_value=HttpResponse(status=302)),
    ):
        response = view(assignments.update_assignment)(assignment_request, pk=9)

    assert response.status_code == 302
    update.assert_called_once_with(
        command=UpdatePerformerAssignment(
            assignment_id=9,
            priority="critical",
            notes="new",
            is_active=True,
            alert_on_battery_low=None,
            alert_on_signal_loss=True,
            alert_on_audio_low=None,
            alert_on_hardware_offline=None,
        ),
        user=assignment_request.user,
    )


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PerformerAssignment.DoesNotExist(), 403),
        (PermissionDenied(), 403),
        (ValidationError("invalid update"), 400),
        (RuntimeError("broken update"), 500),
    ],
)
def test_update_assignment_maps_service_errors(error: Exception, status: int) -> None:
    assignment = _assignment()
    with (
        patch.object(assignments.PerformerAssignment.objects, "for_user", return_value="visible"),
        patch.object(assignments, "get_object_or_404", return_value=assignment),
        patch.object(
            assignments.PerformerAssignmentService, "update_assignment", side_effect=error
        ),
        patch.object(assignments, "_assignment_form_context", return_value={}) as context,
        patch.object(
            assignments,
            "render",
            side_effect=lambda *_args, **kwargs: HttpResponse(status=kwargs.get("status", 200)),
        ),
    ):
        response = view(assignments.update_assignment)(request("post"), pk=9)

    assert response.status_code == status
    if status in {400, 500}:
        error_message = context.call_args.kwargs["error"]
        expected_message = (
            assignments.ASSIGNMENT_FORM_ERROR
            if status == 400
            else assignments.ASSIGNMENT_SAVE_ERROR
        )
        assert error_message == expected_message
        assert str(error) not in error_message


def test_assignment_forms_reject_unknown_priority_before_service_call() -> None:
    create_request = _valid_assignment_request()
    create_request.POST = create_request.POST.copy()
    create_request.POST["priority"] = "urgent"
    assignment = _assignment()
    with (
        patch.object(assignments.PerformerAssignment.objects, "for_user", return_value="visible"),
        patch.object(assignments, "get_object_or_404", return_value=assignment),
        patch.object(assignments.PerformerAssignmentService, "create_assignment") as create,
        patch.object(assignments.PerformerAssignmentService, "update_assignment") as update,
        patch.object(assignments, "_assignment_form_context", return_value={}),
        patch.object(
            assignments,
            "render",
            side_effect=lambda *_args, **kwargs: HttpResponse(status=kwargs.get("status", 200)),
        ),
    ):
        assert view(assignments.create_assignment)(create_request).status_code == 400
        update_request = request("post", data={"priority": "urgent"})
        assert view(assignments.update_assignment)(update_request, pk=9).status_code == 400
    create.assert_not_called()
    update.assert_not_called()


def test_delete_assignment_checks_visibility_before_service_call() -> None:
    assignment_request = request("post")
    with (
        patch.object(assignments.PerformerAssignment.objects, "for_user", return_value="visible"),
        patch.object(assignments, "get_object_or_404") as get_object,
        patch.object(assignments.PerformerAssignmentService, "delete_assignment") as delete,
        patch.object(assignments, "redirect", return_value=HttpResponse(status=302)),
    ):
        response = view(assignments.delete_assignment)(assignment_request, pk=4)
    assert response.status_code == 302
    get_object.assert_called_once()
    delete.assert_called_once_with(assignment_id=4, user=assignment_request.user)
