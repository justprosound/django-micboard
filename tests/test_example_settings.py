"""Regression tests for the example host's optional-app composition."""

import runpy
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import patch


def test_unfold_does_not_enable_import_export_without_its_package() -> None:
    """Each optional admin integration must be usable independently."""
    settings_path = Path(__file__).parents[1] / "example_project" / "settings.py"

    def optional_package(package_name: str) -> ModuleSpec | None:
        if package_name == "unfold":
            return ModuleSpec(package_name, loader=None)
        return None

    with patch("importlib.util.find_spec", side_effect=optional_package):
        namespace = runpy.run_path(str(settings_path))

    installed_apps = namespace["INSTALLED_APPS"]
    assert "unfold" in installed_apps
    assert "unfold.contrib.filters" in installed_apps
    assert "unfold.contrib.import_export" not in installed_apps
    assert "import_export" not in installed_apps
