"""Assignment views for performer-device binding."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from micboard.models import (
    MonitoringGroup,
    Performer,
    PerformerAssignment,
    WirelessUnit,
)


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
    """Create a new performer assignment."""
    if request.method == "GET":
        # Load available performers, units, and groups for the form
        context = {
            "performers": Performer.objects.all(),
            "wireless_units": WirelessUnit.objects.all(),
            "monitoring_groups": _get_user_monitoring_groups(request.user),
        }
        return render(request, "micboard/assignments/form.html", context)

    elif request.method == "POST":
        try:
            with transaction.atomic():
                # Extract and validate form data
                performer_id = request.POST.get("performer_id")
                wireless_unit_id = request.POST.get("wireless_unit_id")
                monitoring_group_id = request.POST.get("monitoring_group_id")
                priority = request.POST.get("priority", "normal")
                notes = request.POST.get("notes", "")
                alert_battery_low = request.POST.get("alert_on_battery_low") == "on"
                alert_signal_loss = request.POST.get("alert_on_signal_loss") == "on"
                alert_audio_low = request.POST.get("alert_on_audio_low") == "on"
                alert_hardware_offline = request.POST.get("alert_on_hardware_offline") == "on"

                # Validate required fields
                if not all([performer_id, wireless_unit_id, monitoring_group_id]):
                    return render(
                        request,
                        "micboard/assignments/form.html",
                        {
                            "error": "Performer, Wireless Unit, and Monitoring Group are required",
                            "performers": Performer.objects.all(),
                            "wireless_units": WirelessUnit.objects.all(),
                            "monitoring_groups": _get_user_monitoring_groups(request.user),
                        },
                    )

                # Get objects and validate user permissions
                performer = get_object_or_404(Performer, pk=performer_id)
                wireless_unit = get_object_or_404(WirelessUnit, pk=wireless_unit_id)
                monitoring_group = get_object_or_404(MonitoringGroup, pk=monitoring_group_id)

                # Check that user has permission to assign to this group
                if (
                    not request.user.is_superuser
                    and monitoring_group not in _get_user_monitoring_groups(request.user)
                ):
                    return HttpResponseForbidden("Unauthorized")

                # Create assignment
                PerformerAssignment.objects.create(
                    performer=performer,
                    wireless_unit=wireless_unit,
                    monitoring_group=monitoring_group,
                    priority=priority,
                    notes=notes,
                    alert_on_battery_low=alert_battery_low,
                    alert_on_signal_loss=alert_signal_loss,
                    alert_on_audio_low=alert_audio_low,
                    alert_on_hardware_offline=alert_hardware_offline,
                    assigned_by=request.user,
                )

                return redirect("assignments")
        except Exception as e:
            return render(
                request,
                "micboard/assignments/form.html",
                {
                    "error": f"Error creating assignment: {str(e)}",
                    "performers": Performer.objects.all(),
                    "wireless_units": WirelessUnit.objects.all(),
                    "monitoring_groups": _get_user_monitoring_groups(request.user),
                },
            )


@require_http_methods(["GET", "POST"])
@login_required
def update_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing assignment."""
    assignment = get_object_or_404(PerformerAssignment, pk=pk)

    # Check user permissions
    if (
        not request.user.is_superuser
        and assignment.monitoring_group not in _get_user_monitoring_groups(request.user)
    ):
        return HttpResponseForbidden("Unauthorized")

    if request.method == "GET":
        context = {
            "assignment": assignment,
            "performers": Performer.objects.all(),
            "wireless_units": WirelessUnit.objects.all(),
            "monitoring_groups": _get_user_monitoring_groups(request.user),
        }
        return render(request, "micboard/assignments/form.html", context)

    elif request.method == "POST":
        try:
            with transaction.atomic():
                # Extract and validate form data
                priority = request.POST.get("priority", assignment.priority)
                notes = request.POST.get("notes", assignment.notes)
                is_active = request.POST.get("is_active") == "on"
                alert_battery_low = request.POST.get("alert_on_battery_low") == "on"
                alert_signal_loss = request.POST.get("alert_on_signal_loss") == "on"
                alert_audio_low = request.POST.get("alert_on_audio_low") == "on"
                alert_hardware_offline = request.POST.get("alert_on_hardware_offline") == "on"

                # Update assignment
                assignment.priority = priority
                assignment.notes = notes
                assignment.is_active = is_active
                assignment.alert_on_battery_low = alert_battery_low
                assignment.alert_on_signal_loss = alert_signal_loss
                assignment.alert_on_audio_low = alert_audio_low
                assignment.alert_on_hardware_offline = alert_hardware_offline
                assignment.save()

                return redirect("assignments")
        except Exception as e:
            return render(
                request,
                "micboard/assignments/form.html",
                {
                    "assignment": assignment,
                    "error": f"Error updating assignment: {str(e)}",
                    "performers": Performer.objects.all(),
                    "wireless_units": WirelessUnit.objects.all(),
                    "monitoring_groups": _get_user_monitoring_groups(request.user),
                },
            )


@require_http_methods(["POST"])
@login_required
def delete_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an assignment."""
    assignment = get_object_or_404(PerformerAssignment, pk=pk)

    # Check user permissions
    if (
        not request.user.is_superuser
        and assignment.monitoring_group not in _get_user_monitoring_groups(request.user)
    ):
        return HttpResponseForbidden("Unauthorized")

    assignment.delete()
    return redirect("assignments")


def _get_user_monitoring_groups(user) -> list:
    """Get monitoring groups the user has access to."""
    if user.is_superuser:
        return list(MonitoringGroup.objects.all())
    return list(user.monitoring_groups.all())
