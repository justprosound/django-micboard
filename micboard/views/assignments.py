"""Assignment views for performer-device binding."""

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.monitoring.monitoring_access import MonitoringService

logger = logging.getLogger(__name__)

ALERT_OPTIONS = (
    ("alert_on_battery_low", "Battery low"),
    ("alert_on_signal_loss", "Signal loss"),
    ("alert_on_audio_low", "Low audio"),
    ("alert_on_hardware_offline", "Hardware offline"),
)


def _assignment_form_context(
    *,
    user: Any,
    assignment: PerformerAssignment | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the user-scoped assignment form context."""
    context: dict[str, Any] = {
        "assignment": assignment,
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


class AssignmentListView(LoginRequiredMixin, ListView):
    """List all performer assignments."""

    model = PerformerAssignment
    template_name = "micboard/assignments.html"
    context_object_name = "assignments"
    paginate_by = 50

    def get_queryset(self):
        """Filter assignments by user permissions and monitoring groups they manage."""
        return PerformerAssignment.objects.for_user(user=self.request.user).select_related(
            "performer", "wireless_unit", "monitoring_group"
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

    # POST: delegate business logic to the service layer
    performer_id = request.POST.get("performer_id")
    wireless_unit_id = request.POST.get("wireless_unit_id")
    monitoring_group_id = request.POST.get("monitoring_group_id")

    # Basic validation and authorization (controller-level)
    if not performer_id or not wireless_unit_id or not monitoring_group_id:
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                error="Performer, Wireless Unit, and Monitoring Group are required",
            ),
        )

    try:
        PerformerAssignmentService.create_assignment(
            performer_id=int(performer_id),
            unit_id=int(wireless_unit_id),
            group_id=int(monitoring_group_id),
            priority=request.POST.get("priority", "normal"),
            notes=request.POST.get("notes", ""),
            alert_on_battery_low=request.POST.get("alert_on_battery_low") == "on",
            alert_on_signal_loss=request.POST.get("alert_on_signal_loss") == "on",
            alert_on_audio_low=request.POST.get("alert_on_audio_low") == "on",
            alert_on_hardware_offline=request.POST.get("alert_on_hardware_offline") == "on",
            user=request.user,
        )
        return redirect("micboard:assignments")
    except PermissionDenied:
        return HttpResponseForbidden("Unauthorized")
    except Exception as exc:
        logger.exception("Failed to create performer assignment")
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                error=f"Error creating assignment: {exc}",
            ),
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

    # POST: delegate update to service
    priority = request.POST.get("priority", assignment.priority)
    notes = request.POST.get("notes", assignment.notes)
    is_active = request.POST.get("is_active") == "on"
    alert_battery_low = request.POST.get("alert_on_battery_low") == "on"
    alert_signal_loss = request.POST.get("alert_on_signal_loss") == "on"
    alert_audio_low = request.POST.get("alert_on_audio_low") == "on"
    alert_hardware_offline = request.POST.get("alert_on_hardware_offline") == "on"

    try:
        PerformerAssignmentService.update_assignment(
            assignment_id=assignment.id,
            user=request.user,
            priority=priority,
            notes=notes,
            is_active=is_active,
            alert_on_battery_low=alert_battery_low,
            alert_on_signal_loss=alert_signal_loss,
            alert_on_audio_low=alert_audio_low,
            alert_on_hardware_offline=alert_hardware_offline,
        )
        return redirect("micboard:assignments")
    except PerformerAssignment.DoesNotExist:
        return HttpResponseForbidden("Assignment not found")
    except PermissionDenied:
        return HttpResponseForbidden("Unauthorized")
    except Exception as exc:
        logger.exception("Failed to update performer assignment %s", assignment.pk)
        return render(
            request,
            "micboard/assignments/form.html",
            _assignment_form_context(
                user=request.user,
                assignment=assignment,
                error=f"Error updating assignment: {exc}",
            ),
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
