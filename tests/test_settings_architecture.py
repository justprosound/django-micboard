"""Architecture contracts for the canonical settings interface."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "micboard"
CANONICAL_SETTINGS_MODULES = {
    PACKAGE / "services" / "settings" / "settings_service.py",
    PACKAGE / "settings" / "deployment_controls.py",
}


def test_micboard_settings_reads_use_the_canonical_interface() -> None:
    """Production modules must not bypass ``SettingsService`` for Micboard settings."""
    bypasses: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        if path in CANONICAL_SETTINGS_MODULES or "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("MICBOARD_"):
                bypasses.append(f"{path.relative_to(ROOT)}:{node.lineno}")
                continue
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "getattr" or len(node.args) < 2:
                continue
            setting_name = node.args[1]
            if (
                isinstance(setting_name, ast.Constant)
                and isinstance(setting_name.value, str)
                and setting_name.value.startswith("MICBOARD_")
            ):
                bypasses.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert bypasses == []
