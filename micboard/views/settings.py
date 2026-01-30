"""Views for settings management interface."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import FormView

from micboard.forms.settings import BulkSettingConfigForm, ManufacturerSettingsForm
from micboard.models.settings import Setting, SettingDefinition


def _is_sensitive_key(key: str) -> bool:
    """Return True when a setting key likely contains secrets."""
    key_lower = key.lower()
    sensitive_tokens = ("secret", "token", "password", "shared_key", "api_key", "key")
    return any(token in key_lower for token in sensitive_tokens)


def _format_value(value: Any, *, sensitive: bool) -> str:
    """Format a value for display in the admin diff view."""
    if value is None:
        return "—"
    if sensitive:
        return "••••••"
    return str(value)


def _resolve_organization_names(org_ids: set[int]) -> dict[int, str]:
    """Resolve organization IDs to names when available."""
    try:
        from micboard.multitenancy.models import Organization
    except Exception:
        return {}

    return dict(Organization.objects.filter(id__in=org_ids).values_list("id", "name"))


def _resolve_manufacturer_names(manufacturer_ids: set[int]) -> dict[int, str]:
    """Resolve manufacturer IDs to names when available."""
    try:
        from micboard.models.discovery import Manufacturer
    except Exception:
        return {}

    return dict(Manufacturer.objects.filter(id__in=manufacturer_ids).values_list("id", "name"))


@staff_member_required
def settings_diff_view(request: HttpRequest) -> HttpResponse:
    """Show where tenant/site/manufacturer settings differ from global defaults."""
    definitions = SettingDefinition.objects.filter(is_active=True).order_by(
        "scope",
        "key",
    )
    raw_overrides: list[dict[str, Any]] = []

    org_ids: set[int] = set()
    manufacturer_ids: set[int] = set()

    for definition in definitions:
        org_overrides = list(
            Setting.objects.filter(definition=definition, organization_id__isnull=False)
        )
        site_overrides = list(
            Setting.objects.filter(definition=definition, site__isnull=False).select_related("site")
        )
        mfg_overrides = list(
            Setting.objects.filter(definition=definition, manufacturer_id__isnull=False)
        )

        if not (org_overrides or site_overrides or mfg_overrides):
            continue

        org_ids.update(
            {override.organization_id for override in org_overrides if override.organization_id}
        )
        manufacturer_ids.update(
            {override.manufacturer_id for override in mfg_overrides if override.manufacturer_id}
        )

        global_setting = Setting.objects.filter(
            definition=definition,
            organization_id__isnull=True,
            site__isnull=True,
            manufacturer_id__isnull=True,
        ).first()

        sensitive = _is_sensitive_key(definition.key)
        global_value = _format_value(
            global_setting.get_parsed_value() if global_setting else None,
            sensitive=sensitive,
        )

        raw_overrides.append(
            {
                "key": definition.key,
                "label": definition.label,
                "global": global_value,
                "sensitive": sensitive,
                "org_overrides": org_overrides,
                "site_overrides": site_overrides,
                "mfg_overrides": mfg_overrides,
            }
        )

    org_names = _resolve_organization_names(org_ids)
    mfg_names = _resolve_manufacturer_names(manufacturer_ids)

    overrides: list[dict[str, Any]] = []
    for override in raw_overrides:
        sensitive = override["sensitive"]

        org_items = [
            {
                "label": org_names.get(item.organization_id, f"Org {item.organization_id}"),
                "value": _format_value(item.get_parsed_value(), sensitive=sensitive),
            }
            for item in override["org_overrides"]
        ]

        site_items = [
            {
                "label": item.site.name if item.site else f"Site {item.site_id}",
                "value": _format_value(item.get_parsed_value(), sensitive=sensitive),
            }
            for item in override["site_overrides"]
        ]

        mfg_items = [
            {
                "label": mfg_names.get(
                    item.manufacturer_id, f"Manufacturer {item.manufacturer_id}"
                ),
                "value": _format_value(item.get_parsed_value(), sensitive=sensitive),
            }
            for item in override["mfg_overrides"]
        ]

        overrides.append(
            {
                "key": override["key"],
                "label": override["label"],
                "global": override["global"],
                "org_overrides": org_items,
                "site_overrides": site_items,
                "mfg_overrides": mfg_items,
            }
        )

    context = {
        "title": "Settings Overrides Diff",
        "overrides": overrides,
    }
    return render(request, "admin/micboard/settings_diff_stub.html", context)


class BulkSettingConfigView(LoginRequiredMixin, FormView):
    """Bulk configure settings for a specific scope."""

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


class ManufacturerSettingsView(LoginRequiredMixin, FormView):
    """Quick configuration view for manufacturer-specific settings."""

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
def settings_overview(request: HttpRequest) -> HttpResponse:
    """Show overview of all configured settings."""
    from micboard.models.settings import Setting

    # Group settings by scope
    global_settings = Setting.objects.filter(
        scope=SettingDefinition.SCOPE_GLOBAL,
    ).select_related("definition")

    org_settings = Setting.objects.filter(
        scope=SettingDefinition.SCOPE_ORGANIZATION,
    ).select_related("definition", "organization")

    site_settings = Setting.objects.filter(
        scope=SettingDefinition.SCOPE_SITE,
    ).select_related("definition", "site")

    mfg_settings = Setting.objects.filter(
        scope=SettingDefinition.SCOPE_MANUFACTURER,
    ).select_related("definition", "manufacturer")

    context = {
        "title": "Settings Overview",
        "global_settings": global_settings,
        "org_settings": org_settings,
        "site_settings": site_settings,
        "mfg_settings": mfg_settings,
    }

    return render(request, "micboard/settings/overview.html", context)
