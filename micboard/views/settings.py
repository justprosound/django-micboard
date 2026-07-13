"""Views for settings management interface."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import FormView

from micboard.forms.settings import BulkSettingConfigForm, ManufacturerSettingsForm
from micboard.services.settings import settings


@staff_member_required
@permission_required("micboard.view_setting", raise_exception=True)
def settings_diff_view(request: HttpRequest) -> HttpResponse:
    """Show where tenant/site/manufacturer settings differ from global defaults."""
    context = settings.get_settings_diff()
    return render(request, "admin/micboard/settings_diff_stub.html", context)


class BulkSettingConfigView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Bulk configure settings for a specific scope."""

    permission_required = ("micboard.add_setting", "micboard.change_setting")
    raise_exception = True
    template_name = "micboard/settings/bulk_config.html"
    form_class = BulkSettingConfigForm
    success_url = reverse_lazy("admin:micboard_setting_changelist")

    def form_valid(self, form: BulkSettingConfigForm) -> HttpResponse:
        """Save settings and show results."""
        try:
            results = form.save_settings()

            if results["saved"] > 0:
                messages.success(
                    self.request,
                    f"✅ {results['saved']} setting(s) updated successfully",
                )

            if results["errors"]:
                for error in results["errors"]:
                    messages.error(self.request, f"❌ {error}")

            return redirect(self.success_url)

        except Exception as e:
            messages.error(self.request, f"❌ Error saving settings: {e}")
            return self.form_invalid(form)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Configure Settings"
        context["description"] = "Configure settings for a specific scope"
        return context


class ManufacturerSettingsView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Quick configuration view for manufacturer-specific settings."""

    permission_required = ("micboard.add_setting", "micboard.change_setting")
    raise_exception = True
    template_name = "micboard/settings/manufacturer_config.html"
    form_class = ManufacturerSettingsForm
    success_url = reverse_lazy("admin:micboard_setting_changelist")

    def form_valid(self, form: ManufacturerSettingsForm) -> HttpResponse:
        """Save manufacturer settings and show results."""
        try:
            results = form.save_settings()
            manufacturer = form.cleaned_data["manufacturer"]

            if results["saved"] > 0:
                messages.success(
                    self.request,
                    f"✅ Updated {results['saved']} setting(s) for {manufacturer.name}",
                )

            if results["errors"]:
                for error in results["errors"]:
                    messages.error(self.request, f"❌ {error}")

            return redirect(self.success_url)

        except Exception as e:
            messages.error(self.request, f"❌ Error saving settings: {e}")
            return self.form_invalid(form)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Configure Manufacturer Settings"
        context["description"] = "Quickly configure settings for a specific manufacturer"
        return context


@login_required
@permission_required("micboard.view_setting", raise_exception=True)
def settings_overview(request: HttpRequest) -> HttpResponse:
    """Show overview of all configured settings."""
    return render(request, "micboard/settings/overview.html", settings.get_settings_overview())
