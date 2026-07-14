"""Behavioral coverage for EFIS import and settings initialization commands."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, Mock

import pytest

from micboard.management.commands import import_efis_regulations as efis_command
from micboard.management.commands import init_settings as init_command


def test_efis_command_skips_fresh_data(monkeypatch) -> None:
    monkeypatch.setattr(efis_command.EFISImportService, "is_outdated", Mock(return_value=False))
    monkeypatch.setattr(
        efis_command.EFISImportService,
        "get_last_import_date",
        Mock(return_value=datetime(2026, 1, 1)),
    )
    output = StringIO()
    command = efis_command.Command(stdout=output)
    command.handle(force=False, verbose=False)
    assert "EFIS data is fresh" in output.getvalue()


@pytest.mark.parametrize("success", [True, False])
def test_efis_command_reports_import_result(monkeypatch, success: bool) -> None:
    monkeypatch.setattr(efis_command.time, "time", Mock(side_effect=[10.0, 12.0]))
    monkeypatch.setattr(efis_command.EFISImportService, "is_outdated", Mock(return_value=True))
    monkeypatch.setattr(
        efis_command.EFISImportService, "get_last_import_date", Mock(return_value=None)
    )
    result = {"success": success, "message": "done" if success else "failed"}
    if success:
        result.update(domains_updated=1, bands_created=2, bands_updated=3)
    monkeypatch.setattr(efis_command.EFISImportService, "run_import", Mock(return_value=result))
    output = StringIO()
    command = efis_command.Command(stdout=output)

    command.handle(force=True, verbose=True)

    text = output.getvalue()
    assert "Fetching regions" in text
    if success:
        assert "Regulatory domains updated: 1" in text
        assert "2.00 seconds" in text
    else:
        assert "Import failed: failed" in text


def test_efis_command_reports_previous_import(monkeypatch) -> None:
    previous = datetime(2026, 1, 1)
    monkeypatch.setattr(efis_command.time, "time", Mock(side_effect=[1.0, 2.0]))
    monkeypatch.setattr(
        efis_command.EFISImportService, "get_last_import_date", Mock(return_value=previous)
    )
    monkeypatch.setattr(
        efis_command.EFISImportService,
        "run_import",
        Mock(return_value={"success": False, "message": "offline"}),
    )
    output = StringIO()
    efis_command.Command(stdout=output).handle(force=True, verbose=False)
    assert f"Last import: {previous}" in output.getvalue()


def test_init_settings_reset_defaults_and_creation_counts(monkeypatch) -> None:
    all_definitions = MagicMock()
    monkeypatch.setattr(
        init_command.SettingDefinition.objects, "all", Mock(return_value=all_definitions)
    )
    monkeypatch.setattr(
        init_command.ManufacturerConfigRegistry,
        "initialize_defaults",
        Mock(),
    )
    command = init_command.Command(stdout=StringIO())
    command._initialize_definitions = Mock(return_value=4)
    command.handle(reset=True, manufacturer_defaults=True)
    all_definitions.delete.assert_called_once_with()
    init_command.ManufacturerConfigRegistry.initialize_defaults.assert_called_once_with()

    created_definition = object()
    monkeypatch.setattr(
        init_command.SettingDefinition.objects,
        "get_or_create",
        Mock(side_effect=[(created_definition, True), *[(created_definition, False)] * 16]),
    )
    command = init_command.Command(stdout=StringIO())
    assert command._initialize_definitions() == 1
    assert init_command.SettingDefinition.objects.get_or_create.call_count == 17


def test_init_settings_without_optional_actions(monkeypatch) -> None:
    command = init_command.Command(stdout=StringIO())
    command._initialize_definitions = Mock(return_value=0)
    delete = Mock()
    monkeypatch.setattr(init_command.SettingDefinition.objects, "all", delete)
    initialize = Mock()
    monkeypatch.setattr(init_command.ManufacturerConfigRegistry, "initialize_defaults", initialize)
    command.handle(reset=False, manufacturer_defaults=False)
    delete.assert_not_called()
    initialize.assert_not_called()
