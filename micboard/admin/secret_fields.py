"""Helpers for keeping raw secret fields out of readonly admin rendering."""

from __future__ import annotations

from typing import Any


def replace_field(
    fieldsets: tuple[Any, ...],
    *,
    raw_field: str,
    display_field: str,
) -> list[tuple[Any, dict[str, Any]]]:
    """Replace a model field with a safe readonly display in every fieldset."""
    safe_fieldsets: list[tuple[Any, dict[str, Any]]] = []
    for title, options in fieldsets:
        safe_options = dict(options)
        safe_options["fields"] = tuple(
            display_field if field_name == raw_field else field_name
            for field_name in options["fields"]
        )
        safe_fieldsets.append((title, safe_options))
    return safe_fieldsets
