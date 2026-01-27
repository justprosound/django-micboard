"""Assignment views for performer-device binding."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import ListView

from micboard.models import PerformerAssignment


class AssignmentListView(ListView):
    """List all performer assignments."""

    model = PerformerAssignment
    template_name = "micboard/assignments/list.html"
    context_object_name = "assignments"
    paginate_by = 50

    def get_queryset(self):
        """Filter assignments by user permissions."""
        # TODO: Implement user-based filtering
        return PerformerAssignment.objects.all().select_related(
            "performer", "wireless_unit", "monitoring_group"
        )


@login_required
def create_assignment(request: HttpRequest) -> HttpResponse:
    """Create a new performer assignment."""
    if request.method == "GET":
        return render(request, "micboard/assignments/form.html", {})
    elif request.method == "POST":
        # TODO: Implement create logic with form validation
        return redirect("assignments")
    return HttpResponse("Method not allowed", status=405)


@login_required
def update_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing assignment."""
    try:
        assignment = PerformerAssignment.objects.get(pk=pk)
    except PerformerAssignment.DoesNotExist:
        return HttpResponse("Not found", status=404)

    if request.method == "GET":
        return render(request, "micboard/assignments/form.html", {"assignment": assignment})
    elif request.method == "POST":
        # TODO: Implement update logic with form validation
        return redirect("assignments")
    return HttpResponse("Method not allowed", status=405)


@login_required
def delete_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an assignment."""
    try:
        assignment = PerformerAssignment.objects.get(pk=pk)
    except PerformerAssignment.DoesNotExist:
        return HttpResponse("Not found", status=404)

    if request.method == "POST":
        assignment.delete()
        return redirect("assignments")

    return render(request, "micboard/assignments/confirm_delete.html", {"assignment": assignment})
