"""Assignment views for performer-device binding."""

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from micboard.forms.assignments import CreateAssignmentForm, UpdateAssignmentForm
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from micboard.services.monitoring.monitoring_access import MonitoringService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

ALERT_OPTIONS = (
    ("alert_on_battery_low", "Battery low"),
    ("alert_on_signal_loss", "Signal loss"),
    ("alert_on_audio_low", "Low audio"),
    ("alert_on_hardware_offline", "Hardware offline"),
)
ASSIGNMENT_SAVE_ERROR = "Unable to save the assignment. Please try again."
ASSIGNMENT_FORM_ERROR = "Correct the invalid assignment values and try again."


def _assignment_form_context(
    *,
    user: Any,
    assignment: PerformerAssignment | None = None,
    error: str | None = None,
    form: CreateAssignmentForm | UpdateAssignmentForm | None = None,
) -> dict[str, Any]:
    """Build the user-scoped assignment form context."""
    context: dict[str, Any] = {
        "assignment": assignment,
        "form": form,
        "performers": Performer.objects.for_user(user=user),
        "wireless_units": WirelessUnit.objects.for_user(user=user),
        "monitoring_groups": MonitoringService.get_user_monitoring_groups(user),
        "priority_choices": PerformerAssignment.PRIORITY_CHOICES,
        "selected_priority": assignment.priority if assignment else "normal",
        "alert_options": [
            {
                "name": name,
                "label": label,
                "checked": getattr(assignment, name, name != "alert_on_audio_low"),
            }
            for name, label in ALERT_OPTIONS
        ],
    }
    if error:
        context["error"] = error
    return context


def _optional_form_value(
    form: CreateAssignmentForm | UpdateAssignmentForm,
    field_name: str,
) -> Any:
    """Return a cleaned value only when the client submitted that field."""
    return form.cleaned_data[field_name] if field_name in form.data else None


class AssignmentListView(LoginRequiredMixin, ListView):
    """List all performer assignments."""

    model = PerformerAssignment
    template_name = "micboard/assignments.html"
    context_object_name = "assignments"
    paginate_by: int | None = PerformerAssignmentService.PAGE_SIZE

    def get_queryset(self) -> QuerySet[PerformerAssignment]:
        """Filter assignments by user permissions and monitoring groups they manage."""
        return PerformerAssignmentService.get_visible_assignments(user=self.request.user)


class AssignmentRowsView(AssignmentListView):
    """Render only the bounded assignment rows used for live refreshes."""

    template_name = "micboard/partials/assignment_rows.html"
    paginate_by = None

    def get_queryset(self) -> QuerySet[PerformerAssignment]:
        """Return the requested row slice without full-page pagination metadata."""
        return PerformerAssignmentService.get_visible_assignment_rows(
            user=self.request.user,
            page=self.request.GET.get("page", 1),
        )


@require_http_methods(["GET", "POST"])
@login_required
def create_assignment(request: HttpRequest) -> HttpResponse:
    """Create a new performer assignment (delegates to PerformerAssignmentService)."""
    if request.method == "GET":
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(user=request.user),
        )

    form = CreateAssignmentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                error=ASSIGNMENT_FORM_ERROR,
                form=form,
            ),
            status=400,
        )

    cleaned = form.cleaned_data
    try:
        command = CreatePerformerAssignment(
            performer_id=cleaned["performer_id"],
            unit_id=cleaned["wireless_unit_id"],
            group_id=cleaned["monitoring_group_id"],
            priority=cleaned["priority"] or "normal",
            notes=cleaned["notes"],
            alert_on_battery_low=_optional_form_value(form, "alert_on_battery_low"),
            alert_on_signal_loss=_optional_form_value(form, "alert_on_signal_loss"),
            alert_on_audio_low=_optional_form_value(form, "alert_on_audio_low"),
            alert_on_hardware_offline=_optional_form_value(form, "alert_on_hardware_offline"),
        )
        PerformerAssignmentService.create_assignment(command=command, user=request.user)
        return redirect("micboard:assignments")
    except PermissionDenied:
        return HttpResponseForbidden("Unauthorized")
    except ValidationError:
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                error=ASSIGNMENT_FORM_ERROR,
                form=form,
            ),
            status=400,
        )
    except Exception as exc:
        logger.exception(
            "Failed to create performer assignment",
            exc_info=sanitized_exception_info(exc),
        )
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                error=ASSIGNMENT_SAVE_ERROR,
            ),
            status=500,
        )


@require_http_methods(["GET", "POST"])
@login_required
def update_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing assignment (delegates to PerformerAssignmentService)."""
    assignment = get_object_or_404(
        PerformerAssignment.objects.for_user(user=request.user),
        pk=pk,
    )

    if request.method == "GET":
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(user=request.user, assignment=assignment),
        )

    form = UpdateAssignmentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                assignment=assignment,
                error=ASSIGNMENT_FORM_ERROR,
                form=form,
            ),
            status=400,
        )

    cleaned = form.cleaned_data
    try:
        command = UpdatePerformerAssignment(
            assignment_id=assignment.id,
            priority=cleaned["priority"] or None,
            notes=_optional_form_value(form, "notes"),
            is_active=_optional_form_value(form, "is_active"),
            alert_on_battery_low=_optional_form_value(form, "alert_on_battery_low"),
            alert_on_signal_loss=_optional_form_value(form, "alert_on_signal_loss"),
            alert_on_audio_low=_optional_form_value(form, "alert_on_audio_low"),
            alert_on_hardware_offline=_optional_form_value(form, "alert_on_hardware_offline"),
        )
        PerformerAssignmentService.update_assignment(command=command, user=request.user)
        return redirect("micboard:assignments")
    except PerformerAssignment.DoesNotExist:
        return HttpResponseForbidden("Assignment not found")
    except PermissionDenied:
        return HttpResponseForbidden("Unauthorized")
    except ValidationError:
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                assignment=assignment,
                error=ASSIGNMENT_FORM_ERROR,
                form=form,
            ),
            status=400,
        )
    except Exception as exc:
        logger.exception(
            "Failed to update performer assignment %s",
            assignment.pk,
            exc_info=sanitized_exception_info(exc),
        )
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                assignment=assignment,
                error=ASSIGNMENT_SAVE_ERROR,
            ),
            status=500,
        )


@require_http_methods(["POST"])
@login_required
def delete_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an assignment (delegates to PerformerAssignmentService)."""
    get_object_or_404(
        PerformerAssignment.objects.for_user(user=request.user),
        pk=pk,
    )

    PerformerAssignmentService.delete_assignment(assignment_id=pk, user=request.user)
    return redirect("micboard:assignments")
