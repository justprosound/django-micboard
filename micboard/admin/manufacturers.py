from __future__ import annotations

import logging
import pkgutil
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

import micboard.integrations
from micboard.admin.mixins import MicboardModelAdmin
from micboard.admin.secret_fields import replace_field
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.services.manufacturer.secret_redaction import (
    redact_secrets,
    restore_redacted_secrets,
)
from micboard.services.sync.discovery_candidates_service import DiscoveryCandidateService
from micboard.services.sync.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)


class ManufacturerAdminForm(forms.ModelForm):
    """Form for Manufacturer admin with auto-discovered code choices."""

    class Meta:
        model = Manufacturer
        fields = ["name", "code", "is_active", "config"]

    def __init__(self, *args, **kwargs):
        """Initialize the manufacturer admin form and populate plugin choices."""
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["config"] = redact_secrets(self.instance.config)
        # Dynamically populate manufacturer code choices from available plugins
        plugin_codes = []
        try:
            # Get all available plugin codes from the registry
            for _finder, name, _ispkg in pkgutil.iter_modules(micboard.integrations.__path__):
                try:
                    get_manufacturer_plugin(name)
                    plugin_codes.append((name, name.capitalize()))
                except Exception:
                    logger.debug("Skipping unavailable manufacturer plugin %s", name, exc_info=True)
                    continue
        except Exception:
            plugin_codes = []
        if plugin_codes:
            self.fields["code"].widget = forms.Select(choices=plugin_codes)
            self.fields["code"].help_text += " (auto-discovered from available plugins)"

    def clean_config(self) -> dict[str, Any]:
        """Preserve unchanged redacted credentials in manufacturer JSON."""
        config = self.cleaned_data.get("config") or {}
        original = self.instance.config if self.instance.pk else {}
        return restore_redacted_secrets(config, original)


@admin.register(Manufacturer)
class ManufacturerAdmin(MicboardModelAdmin):
    """Admin for Manufacturer with a view to manage discovery IPs and plugin selection."""

    form = ManufacturerAdminForm
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")
    readonly_fields = ("settings_link", "config_redacted")
    fieldsets = (
        ("Manufacturer", {"fields": ("name", "code", "is_active")}),
        ("Plugin Configuration", {"fields": ("config",)}),
        ("Scoped Settings", {"fields": ("settings_link",)}),
    )

    @admin.display(description="Manufacturer Settings")
    def settings_link(self, obj: Manufacturer) -> str:
        """Link to the dedicated, persisted manufacturer settings workflow."""
        if not obj.pk:
            return "Save the manufacturer before configuring scoped settings."
        url = f"{reverse('micboard:settings_manufacturer_config')}?manufacturer={obj.pk}"
        return format_html('<a href="{}">Configure scoped settings</a>', url)

    def get_fieldsets(self, request, obj=None):
        """Keep raw plugin JSON out of readonly change pages."""
        if obj is not None and not self.has_change_permission(request, obj):
            return replace_field(
                self.fieldsets,
                raw_field="config",
                display_field="config_redacted",
            )
        return super().get_fieldsets(request, obj)

    @admin.display(description="Plugin Configuration")
    def config_redacted(self, obj: Manufacturer) -> str:
        """Display plugin configuration with credential values masked."""
        import json

        return json.dumps(redact_secrets(obj.config), indent=2, sort_keys=True)

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
        self._check_discovery_permission(request)

        try:
            manufacturer = self._scope_queryset_for_user(
                Manufacturer.objects.all(),
                user=request.user,
            ).get(pk=manufacturer_id)
        except Manufacturer.DoesNotExist:
            self.message_user(
                request,
                f"Manufacturer with ID {manufacturer_id} not found",
                level=messages.ERROR,
            )
            return redirect("admin:micboard_manufacturer_changelist")

        self._check_discovery_permission(request, manufacturer)

        discovery_service = DiscoveryService()
        candidate_service = DiscoveryCandidateService()

        ips: list[str] = []

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
                        request,
                        f"Removed {success_count} IP(s)",
                        level=messages.SUCCESS,
                    )
                else:
                    self.message_user(request, "Failed to remove IP(s)", level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    "No IPs specified or client unavailable",
                    level=messages.WARNING,
                )

            return redirect(
                reverse("admin:micboard_manufacturer_discovery_ips", args=[manufacturer_id])
            )

        # For GET requests, or after POST if not redirected
        try:
            ips = candidate_service.get_discovery_candidates(manufacturer.code)
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

    def _check_discovery_permission(
        self,
        request: Any,
        manufacturer: Manufacturer | None = None,
    ) -> None:
        """Require view access for reads and change access for removals."""
        permission_check = (
            self.has_change_permission if request.method == "POST" else self.has_view_permission
        )
        if not permission_check(request, manufacturer):
            raise PermissionDenied
