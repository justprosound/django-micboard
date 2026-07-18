from typing import Any
from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.views.generic import TemplateView

from micboard.forms.dashboard import DisplayWidthForm
from micboard.models.users.user_profile import UserProfile
from micboard.services.chargers.dashboard_service import ChargerDashboardService
from micboard.services.core.user_profile import UserProfileService


class ChargerDashboardView(LoginRequiredMixin, TemplateView):
    """Render the complete charger dashboard from one typed service snapshot."""

    template_name = "micboard/charger_dashboard.html"

    def get_context_data(self, **kwargs: Any) -> Any:
        """Add display preferences and one primitive charger projection."""
        context = super().get_context_data(**kwargs)
        user = cast(User, self.request.user)
        profile, _created = UserProfile.objects.get_or_create(user=user)
        context["snapshot"] = ChargerDashboardService.get_snapshot(user=user)
        context["display_width_px"] = profile.display_width_px
        context.setdefault(
            "display_width_form",
            DisplayWidthForm(initial={"display_width_px": profile.display_width_px}),
        )
        return context

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        """Handle display width updates."""
        form = DisplayWidthForm(request.POST)
        if not form.is_valid():
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


class ChargerGridView(LoginRequiredMixin, TemplateView):
    """Render only the tenant-scoped charger grid used for live refreshes."""

    template_name = "micboard/partials/charger_grid.html"

    def get_context_data(self, **kwargs: Any) -> Any:
        """Load the typed grid snapshot without full-page profile work."""
        context = super().get_context_data(**kwargs)
        context["snapshot"] = ChargerDashboardService.get_snapshot(user=self.request.user)
        return context
