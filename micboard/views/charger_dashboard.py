from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import ListView

from micboard.models import Charger, PerformerAssignment, UserProfile


class ChargerDashboardView(LoginRequiredMixin, ListView):
    model = Charger
    template_name = "micboard/charger_dashboard.html"
    context_object_name = "chargers"

    def get_queryset(self):
        return Charger.objects.active().prefetch_related("slots").order_by("order", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        context["display_width_px"] = profile.display_width_px

        # Build mapping of serial -> performer info for docked units
        # Get all active assignments with performer info
        serial_to_performer = {}

        assignments = PerformerAssignment.objects.filter(is_active=True).select_related(
            "performer", "wireless_unit"
        )

        for assignment in assignments:
            unit = assignment.wireless_unit
            if unit and unit.serial_number:
                serial_to_performer[unit.serial_number] = {
                    "name": assignment.performer.name,
                    "title": assignment.performer.title or "",
                    "photo_url": assignment.performer.photo.url
                    if assignment.performer.photo
                    else None,
                }

        context["serial_to_performer"] = serial_to_performer
        return context

    def get(self, request, *args, **kwargs):
        if request.headers.get("HX-Request"):
            self.template_name = "micboard/partials/charger_grid.html"
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle display width updates."""
        width = request.POST.get("display_width_px")
        if width:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.display_width_px = int(width)
            profile.save()

        if request.headers.get("HX-Request"):
            return self.get(request, *args, **kwargs)
        return redirect("charger_dashboard")
