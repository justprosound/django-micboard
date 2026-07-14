from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.views.generic import ListView

from micboard.forms.dashboard import DisplayWidthForm
from micboard.models.hardware.charger import Charger
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.users.user_profile import UserProfile
from micboard.services.core.user_profile import UserProfileService


class ChargerDashboardView(LoginRequiredMixin, ListView):
    model = Charger
    template_name = "micboard/charger_dashboard.html"
    context_object_name = "chargers"

    def get_queryset(self):
        return (
            Charger.objects.for_user(user=self.request.user)
            .filter(is_active=True)
            .prefetch_related("slots")
            .order_by("order", "name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = cast(User, self.request.user)
        profile, _created = UserProfile.objects.get_or_create(user=user)
        context["display_width_px"] = profile.display_width_px
        context.setdefault(
            "display_width_form",
            DisplayWidthForm(initial={"display_width_px": profile.display_width_px}),
        )

        # Build mapping of serial -> performer info for docked units
        # Get all active assignments with performer info
        serial_to_performer = {}

        assignments = (
            PerformerAssignment.objects.for_user(user=user)
            .filter(is_active=True)
            .select_related("performer", "wireless_unit")
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
        form = DisplayWidthForm(request.POST)
        if not form.is_valid():
            self.object_list = self.get_queryset()
            return self.render_to_response(
                self.get_context_data(display_width_form=form),
                status=400,
            )

        UserProfileService.set_display_width(
            user=request.user,
            width_px=form.cleaned_data["display_width_px"],
        )

        if request.headers.get("HX-Request"):
            return self.get(request, *args, **kwargs)
        return redirect("micboard:charger_dashboard")
