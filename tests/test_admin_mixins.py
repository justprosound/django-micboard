"""Regression tests for composing optional admin integrations."""

from typing import Any, cast

from django.contrib import admin

from micboard.models.hardware.charger import Charger


def test_sortable_import_export_templates_are_composed() -> None:
    """Import/export must retain admin-sortable's change-list base template."""
    model_admin = cast(Any, admin.site._registry[Charger])

    assert model_admin.change_list_template == "admin/import_export/change_list_import_export.html"
    assert "adminsortable2/change_list.html" in model_admin.ie_base_change_list_template
