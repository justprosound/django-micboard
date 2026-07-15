"""Inline admin components for wireless chassis."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from micboard.admin.mixins import TenantScopedAdminInlineMixin
from micboard.models.integrations import Accessory
from micboard.models.rf_coordination.rf_channel import RFChannel


class RFChannelInlineFormSet(BaseInlineFormSet):
    """Keep active-unit assignments on the inline's own chassis."""

    unit_fields = ("active_wireless_unit", "active_iem_receiver")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        chassis_id = self.instance.pk
        for form in self.forms:
            for field_name in self.unit_fields:
                field = form.fields.get(field_name)
                queryset = getattr(field, "queryset", None)
                if queryset is not None:
                    field.queryset = queryset.filter(base_chassis_id=chassis_id)

    def clean(self) -> None:
        """Reject forged unit assignments even if a custom widget bypasses choices."""
        super().clean()
        chassis_id = self.instance.pk
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            for field_name in self.unit_fields:
                unit = form.cleaned_data.get(field_name)
                if unit is not None and unit.base_chassis_id != chassis_id:
                    form.add_error(
                        field_name,
                        "Selected wireless unit must belong to this chassis.",
                    )


class RFChannelInline(TenantScopedAdminInlineMixin, admin.StackedInline):
    """Tenant-scoped RF channel editor embedded in chassis admin."""

    model = RFChannel
    fk_name = "chassis"
    formset = RFChannelInlineFormSet


class AccessoryInline(TenantScopedAdminInlineMixin, admin.TabularInline):
    """Accessory editor embedded in chassis admin."""

    model = Accessory
    extra = 1
    fields = (
        "category",
        "name",
        "assigned_to",
        "condition",
        "is_available",
        "checked_out_date",
    )
    readonly_fields = ("created_at",)
