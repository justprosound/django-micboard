from __future__ import annotations

import logging
import pkgutil
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

import micboard.integrations
from micboard.admin.mixins import MicboardModelAdmin
from micboard.forms.settings import ManufacturerSettingsForm
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer
from micboard.services.discovery_service_new import DiscoveryService

logger = logging.getLogger(__name__)


class ManufacturerAdminForm(forms.ModelForm):
    """Form for Manufacturer admin with auto-discovered code choices."""

    class Meta:
        model = Manufacturer
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """Initialize the manufacturer admin form and populate plugin choices."""
        super().__init__(*args, **kwargs)
        # Dynamically populate manufacturer code choices from available plugins
        plugin_codes = []
        try:
            # Get all available plugin codes from the registry
            for _finder, name, _ispkg in pkgutil.iter_modules(micboard.integrations.__path__):
                try:
                    get_manufacturer_plugin(name)
                    plugin_codes.append((name, name.capitalize()))
                except Exception:
                    continue
        except Exception:
            plugin_codes = []
        if plugin_codes:
            self.fields["code"].widget = forms.Select(choices=plugin_codes)
            self.fields["code"].help_text += " (auto-discovered from available plugins)"


@admin.register(Manufacturer)
class ManufacturerAdmin(MicboardModelAdmin):
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Add a dedicated fieldset for manufacturer settings
        # Split settings into common and advanced (example: first 4 are common, rest advanced)
        all_fields = [
            name for name in ManufacturerSettingsForm.base_fields if name != "manufacturer"
        ]
        common_fields = all_fields[:4]
        advanced_fields = all_fields[4:]
        if all_fields:
            # Attempt to provide a plugin documentation link if available
            doc_url = None
            if obj:
                try:
                    plugin_class = obj.get_plugin_class()
                    doc_url = getattr(plugin_class, "doc_url", None)
                except Exception:
                    doc_url = None
            help_text = "Configure manufacturer-specific thresholds, timeouts, and feature flags."
            if doc_url:
                help_text += f" <a href='{doc_url}' target='_blank' style='margin-left:1em;'>Plugin Documentation</a>"
            fieldsets = list(fieldsets)
            if common_fields:
                fieldsets.append(
                    (
                        "Manufacturer Settings",
                        {
                            "fields": common_fields,
                            "description": help_text,
                        },
                    )
                )
            if advanced_fields:
                fieldsets.append(
                    (
                        "Advanced Settings",
                        {
                            "fields": advanced_fields,
                            "classes": ("collapse",),
                            "description": "Advanced or rarely-changed options. Edit with care.",
                        },
                    )
                )
        return fieldsets

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class AdminWithSettingsForm(form):
            def __init__(self, *args, **kw):
                """Wrap the admin form and inject manufacturer settings fields when editing."""
                super().__init__(*args, **kw)
                if obj:
                    settings_form = ManufacturerSettingsForm(initial={"manufacturer": obj.pk})
                    for name, field in settings_form.fields.items():
                        if name != "manufacturer":
                            self.fields[name] = field
                            self.initial[name] = settings_form.initial.get(name, None)

        return AdminWithSettingsForm

        def save_model(self, request, obj, form, change):
            super().save_model(request, obj, form, change)
            # Save manufacturer settings if present
            settings_data = {
                k: v
                for k, v in form.cleaned_data.items()
                if k in ManufacturerSettingsForm.base_fields
            }
            if settings_data:
                settings_form = ManufacturerSettingsForm({**settings_data, "manufacturer": obj.pk})
                if settings_form.is_valid():
                    settings_form.save_settings()

    """Admin for Manufacturer with a view to manage discovery IPs and plugin selection."""

    form = ManufacturerAdminForm
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")

    def save_model(self, request, obj, form, change):
        """Log creation or modification in both audit and admin logs."""
        super().save_model(request, obj, form, change)
        if change:
            obj._log_change(action="modified")
            self.log_change(request, obj, "Manufacturer modified via admin.")
        else:
            obj._log_change(action="created")
            self.log_addition(request, obj, "Manufacturer created via admin.")

    def delete_model(self, request, obj):
        """Log deletion in both audit and admin logs."""
        obj._log_change(action="deleted")
        self.log_deletion(request, obj, "Manufacturer deleted via admin.")
        super().delete_model(request, obj)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:manufacturer_id>/discovery-ips/",
                self.admin_site.admin_view(self.discovery_ips_view),
                name="micboard_manufacturer_discovery_ips",
            ),
        ]
        return custom_urls + urls

    def discovery_ips_view(self, request, manufacturer_id: int):
        """Display and manage discovery IPs for a manufacturer.

        GET: Show current discovery IPs.
        POST: Remove selected IP(s).
        """
        try:
            manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        except Manufacturer.DoesNotExist:
            self.message_user(
                request,
                f"Manufacturer with ID {manufacturer_id} not found",
                level=messages.ERROR,
            )
            return redirect("admin:micboard_manufacturer_changelist")

        discovery_service = DiscoveryService()  # Instantiate DiscoveryService

        ips: list[str] = []  # Initialize ips once

        if request.method == "POST":
            ips_to_remove = request.POST.getlist("remove_ip") or request.POST.getlist("remove_ips")
            ips_to_remove = [ip for ip in ips_to_remove if ip]
            if ips_to_remove:
                success_count = 0
                for ip in ips_to_remove:
                    if discovery_service.remove_discovery_candidate(ip, manufacturer):
                        success_count += 1

                if success_count > 0:
                    self.message_user(
                        request, f"Removed {success_count} IP(s)", level=messages.SUCCESS
                    )
                else:
                    self.message_user(request, "Failed to remove IP(s)", level=messages.ERROR)
            else:
                self.message_user(
                    request, "No IPs specified or client unavailable", level=messages.WARNING
                )

            return redirect(
                reverse("admin:micboard_manufacturer_discovery_ips", args=[manufacturer_id])
            )

        # For GET requests, or after POST if not redirected
        try:
            ips = discovery_service.get_discovery_candidates(manufacturer.code)
        except Exception as e:
            logger.exception("Failed to fetch discovery IPs for %s: %s", manufacturer.code, e)
            self.message_user(request, f"Failed to fetch discovery IPs: {e}", level=messages.ERROR)

        context: dict[str, Any] = {
            "manufacturer": manufacturer,
            "ips": ips,
            "opts": self.model._meta,
            "title": f"Discovery IPs for {manufacturer.name}",
            "show_refresh": getattr(request, "user", None)
            and getattr(request.user, "is_staff", False),
        }
        return render(request, "admin/micboard/manufacturer_discovery_ips.html", context)
