"""Forms for manufacturer configuration JSON."""

from typing import TYPE_CHECKING, Any

from django import forms

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.services.manufacturer.secret_redaction import (
    redact_secrets,
    restore_redacted_secrets,
)

if TYPE_CHECKING:
    _ManufacturerConfigurationForm = forms.ModelForm[ManufacturerConfiguration]
else:
    _ManufacturerConfigurationForm = forms.ModelForm


class ManufacturerConfigurationForm(_ManufacturerConfigurationForm):
    """Edit configuration JSON without disclosing stored credentials."""

    config = forms.JSONField(required=False, widget=forms.Textarea)

    class Meta:
        model = ManufacturerConfiguration
        fields = ("code", "name", "is_active", "config", "updated_by")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["config"] = redact_secrets(self.instance.config)

    def clean_config(self) -> Any:
        """Preserve secrets represented by unchanged redaction placeholders."""
        config = self.cleaned_data.get("config") or {}
        original = self.instance.config if self.instance.pk else {}
        return restore_redacted_secrets(config, original)
