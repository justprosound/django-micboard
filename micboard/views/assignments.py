from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from micboard.models import DeviceAssignment, RFChannel

User = get_user_model()


class AssignmentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """View for Technicians to manage Performer-Channel assignments."""

    model = DeviceAssignment
    template_name = "micboard/assignments.html"
    context_object_name = "assignments"
    permission_required = "micboard.change_deviceassignment"

    def get_queryset(self):
        return (
            DeviceAssignment.objects.active()
            .select_related("user__profile", "channel__chassis", "channel__chassis__manufacturer")
            .order_by("channel__chassis__name", "channel__channel_number")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Provide lists for the create/edit forms
        context["performers"] = User.objects.filter(profile__user_type="performer").order_by(
            "username"
        )
        context["channels"] = (
            RFChannel.objects.filter(enabled=True)
            .select_related("chassis")
            .order_by("chassis__name", "channel_number")
        )
        return context


def update_assignment(request, pk):
    """HTMX handler to update an assignment."""
    if request.method != "POST":
        return redirect("assignments")

    assignment = get_object_or_404(DeviceAssignment, pk=pk)

    # Simple form handling for now - could be upgraded to Django Forms
    user_id = request.POST.get("user")
    priority = request.POST.get("priority")
    notes = request.POST.get("notes")

    if user_id:
        assignment.user = get_object_or_404(User, pk=user_id)
    if priority:
        assignment.priority = priority
    if notes is not None:
        assignment.notes = notes

    assignment.save()

    # Return the updated row partial
    context = {
        "assignment": assignment,
        "performers": User.objects.filter(profile__user_type="performer").order_by("username"),
    }
    return render(request, "micboard/partials/assignment_row.html", context)


def create_assignment(request):
    """HTMX handler to create a new assignment."""
    if request.method != "POST":
        return redirect("assignments")

    user_id = request.POST.get("user")
    channel_id = request.POST.get("channel")
    priority = request.POST.get("priority", "normal")

    if user_id and channel_id:
        user = get_object_or_404(User, pk=user_id)
        channel = get_object_or_404(RFChannel, pk=channel_id)

        DeviceAssignment.objects.create(
            user=user, channel=channel, priority=priority, is_active=True
        )

    return redirect("assignments")


def delete_assignment(request, pk):
    """HTMX handler to delete (deactivate) an assignment."""
    if request.method == "DELETE":
        assignment = get_object_or_404(DeviceAssignment, pk=pk)
        assignment.is_active = False
        assignment.save()
        return render(request, "micboard/partials/empty.html")  # Return empty string to remove row
    return redirect("assignments")
