"""Forms for credential-bearing manufacturer integrations."""

from __future__ import annotations

from django import forms

from micboard.models.integrations import ManufacturerAPIServer


class ManufacturerAPIServerForm(forms.ModelForm):
    """Accept replacement credentials without rendering stored secrets."""

    base_url = forms.URLField(assume_scheme="https")
    shared_key = forms.CharField(
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to preserve the existing shared key.",
    )

    class Meta:
        model = ManufacturerAPIServer
        fields = (
            "name",
            "manufacturer",
            "base_url",
            "shared_key",
            "location_name",
            "enabled",
            "status",
            "status_message",
            "notes",
        )

    def clean_shared_key(self) -> str:
        """Preserve an existing key or require one for a new server."""
        shared_key = self.cleaned_data.get("shared_key", "")
        if shared_key:
            return str(shared_key)
        if self.instance.pk and self.instance.shared_key:
            return str(self.instance.shared_key)
        raise forms.ValidationError("A shared key is required.")
