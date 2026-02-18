"""Assignment views for performer-device binding."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services import AccessControlService, PerformerAssignmentService


class AssignmentListView(LoginRequiredMixin, ListView):
    """List all performer assignments."""

    model = PerformerAssignment
    template_name = "micboard/assignments.html"
    context_object_name = "assignments"
    paginate_by = 50

    def get_queryset(self):
        """Filter assignments by user permissions and monitoring groups they manage."""
        user = self.request.user
        if user.is_superuser:
            return PerformerAssignment.objects.all().select_related(
                "performer", "wireless_unit", "monitoring_group"
            )

        # Filter to monitoring groups the user is a member of
        user_groups = MonitoringGroup.objects.filter(members=user)
        return PerformerAssignment.objects.filter(monitoring_group__in=user_groups).select_related(
            "performer", "wireless_unit", "monitoring_group"
        )


@require_http_methods(["GET", "POST"])
@login_required
def create_assignment(request: HttpRequest) -> HttpResponse:
    """Create a new performer assignment (delegates to PerformerAssignmentService)."""
    if request.method == "GET":
        # Load available performers, units, and groups for the form
        context = {
            "performers": Performer.objects.all(),
            "wireless_units": WirelessUnit.objects.all(),
            "monitoring_groups": AccessControlService.get_user_monitoring_groups(request.user),
        }
        return render(request, "micboard/assignments/form.html", context)

    # POST: delegate business logic to the service layer
    performer_id = request.POST.get("performer_id")
    wireless_unit_id = request.POST.get("wireless_unit_id")
    monitoring_group_id = request.POST.get("monitoring_group_id")

    # Basic validation and authorization (controller-level)
    if not all([performer_id, wireless_unit_id, monitoring_group_id]):
        return render(
            request,
            "micboard/assignments/form.html",
            {
                "error": "Performer, Wireless Unit, and Monitoring Group are required",
                "performers": Performer.objects.all(),
                "wireless_units": WirelessUnit.objects.all(),
                "monitoring_groups": AccessControlService.get_user_monitoring_groups(request.user),
            },
        )

    monitoring_group = get_object_or_404(MonitoringGroup, pk=monitoring_group_id)
    if (
        not request.user.is_superuser
        and monitoring_group not in AccessControlService.get_user_monitoring_groups(request.user)
    ):
        return HttpResponseForbidden("Unauthorized")

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
        return redirect("assignments")
    except Exception as exc:
        return render(
            request,
            "micboard/assignments/form.html",
            {
                "error": f"Error creating assignment: {exc}",
                "performers": Performer.objects.all(),
                "wireless_units": WirelessUnit.objects.all(),
                "monitoring_groups": AccessControlService.get_user_monitoring_groups(request.user),
            },
        )


@require_http_methods(["GET", "POST"])
@login_required
def update_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing assignment (delegates to PerformerAssignmentService)."""
    assignment = get_object_or_404(PerformerAssignment, pk=pk)

    # Check user permissions
    if (
        not request.user.is_superuser
        and assignment.monitoring_group
        not in AccessControlService.get_user_monitoring_groups(request.user)
    ):
        return HttpResponseForbidden("Unauthorized")

    if request.method == "GET":
        context = {
            "assignment": assignment,
            "performers": Performer.objects.all(),
            "wireless_units": WirelessUnit.objects.all(),
            "monitoring_groups": AccessControlService.get_user_monitoring_groups(request.user),
        }
        return render(request, "micboard/assignments/form.html", context)

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
            priority=priority,
            notes=notes,
            is_active=is_active,
            alert_on_battery_low=alert_battery_low,
            alert_on_signal_loss=alert_signal_loss,
            alert_on_audio_low=alert_audio_low,
            alert_on_hardware_offline=alert_hardware_offline,
        )
        return redirect("assignments")
    except PerformerAssignment.DoesNotExist:
        return HttpResponseForbidden("Assignment not found")
    except Exception as exc:
        return render(
            request,
            "micboard/assignments/form.html",
            {
                "assignment": assignment,
                "error": f"Error updating assignment: {exc}",
                "performers": Performer.objects.all(),
                "wireless_units": WirelessUnit.objects.all(),
                "monitoring_groups": AccessControlService.get_user_monitoring_groups(request.user),
            },
        )


@require_http_methods(["POST"])
@login_required
def delete_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an assignment (delegates to PerformerAssignmentService)."""
    assignment = get_object_or_404(PerformerAssignment, pk=pk)

    # Check user permissions
    if (
        not request.user.is_superuser
        and assignment.monitoring_group
        not in AccessControlService.get_user_monitoring_groups(request.user)
    ):
        return HttpResponseForbidden("Unauthorized")

    PerformerAssignmentService.delete_assignment(assignment_id=pk)
    return redirect("assignments")
