"""Focused secret-handling coverage for integration configuration forms."""

from __future__ import annotations

from unittest.mock import patch

from django import forms

import pytest

from micboard.forms.configuration import ManufacturerConfigurationForm
from micboard.forms.integrations import ManufacturerAPIServerForm
from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.integrations import ManufacturerAPIServer


def test_manufacturer_configuration_form_redacts_and_restores_secrets() -> None:
    existing = ManufacturerConfiguration(pk=1, code="vendor", config={"token": "secret"})
    with patch(
        "micboard.forms.configuration.redact_secrets", return_value={"token": "***"}
    ) as redact:
        form = ManufacturerConfigurationForm(instance=existing)
    assert form.initial["config"] == {"token": "***"}
    redact.assert_called_once_with(existing.config)

    form.cleaned_data = {"config": {"token": "***"}}
    with patch(
        "micboard.forms.configuration.restore_redacted_secrets", return_value=existing.config
    ) as restore:
        assert form.clean_config() == existing.config
    restore.assert_called_once_with({"token": "***"}, existing.config)

    new_form = ManufacturerConfigurationForm(instance=ManufacturerConfiguration())
    new_form.cleaned_data = {"config": None}
    with patch("micboard.forms.configuration.restore_redacted_secrets", return_value={}) as restore:
        assert new_form.clean_config() == {}
    restore.assert_called_once_with({}, {})


def test_api_server_form_replaces_preserves_and_requires_shared_key() -> None:
    form = ManufacturerAPIServerForm(instance=ManufacturerAPIServer())
    form.cleaned_data = {"shared_key": " replacement "}
    assert form.clean_shared_key() == " replacement "

    existing = ManufacturerAPIServer(pk=1, shared_key="stored")
    form = ManufacturerAPIServerForm(instance=existing)
    form.cleaned_data = {"shared_key": ""}
    assert form.clean_shared_key() == "stored"

    form = ManufacturerAPIServerForm(instance=ManufacturerAPIServer())
    form.cleaned_data = {"shared_key": ""}
    with pytest.raises(forms.ValidationError, match="required"):
        form.clean_shared_key()
