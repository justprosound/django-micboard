"""Views for settings management interface."""

from __future__ import annotations

import logging
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
from micboard.services.settings.presentation_service import settings_presentation
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


@staff_member_required
@permission_required("micboard.view_setting", raise_exception=True)
def settings_diff_view(request: HttpRequest) -> HttpResponse:
    """Show where tenant/site/manufacturer settings differ from global defaults."""
    context = settings_presentation.get_diff(user=request.user)
    return render(request, "admin/micboard/settings_diff_stub.html", context)


class BulkSettingConfigView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """Bulk configure settings for a specific scope."""

    permission_required = ("micboard.add_setting", "micboard.change_setting")
    raise_exception = True
    template_name = "micboard/settings/bulk_config.html"
    form_class = BulkSettingConfigForm
    success_url = reverse_lazy("admin:micboard_setting_changelist")

    def get_form_kwargs(self) -> dict[str, Any]:
        """Bind tenant visibility to every settings form request."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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

        except Exception as exc:
            logger.exception(
                "Failed to save bulk settings for user %s",
                self.request.user.pk,
                exc_info=sanitized_exception_info(exc),
            )
            messages.error(self.request, "❌ Settings could not be saved. Please try again.")
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

    def get_initial(self) -> dict[str, Any]:
        """Preselect a manufacturer supplied by a trusted admin link."""
        initial = super().get_initial()
        manufacturer_id = self.request.GET.get("manufacturer")
        if manufacturer_id:
            initial["manufacturer"] = manufacturer_id
        return initial

    def get_form_kwargs(self) -> dict[str, Any]:
        """Bind tenant visibility to every manufacturer settings request."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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

        except Exception as exc:
            logger.exception(
                "Failed to save manufacturer settings for user %s",
                self.request.user.pk,
                exc_info=sanitized_exception_info(exc),
            )
            messages.error(self.request, "❌ Settings could not be saved. Please try again.")
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
    return render(
        request,
        "micboard/settings/overview.html",
        settings_presentation.get_overview(user=request.user),
    )
