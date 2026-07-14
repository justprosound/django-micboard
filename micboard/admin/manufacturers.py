from __future__ import annotations

import logging
import pkgutil
from typing import Any

from django import forms
from django.contrib import admin
from django.urls import reverse
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
    """Admin for manufacturer configuration and plugin selection."""

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
