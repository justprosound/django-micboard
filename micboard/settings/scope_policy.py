"""Pure policy helpers for exact settings scopes."""

from __future__ import annotations

from typing import Literal

type SettingsScope = Literal["global", "organization", "site", "manufacturer"]


def resolve_scope(
    *,
    organization_id: int | None,
    site_id: int | None,
    manufacturer_id: int | None,
) -> SettingsScope | None:
    """Return the one exact settings scope, or ``None`` for mixed scopes."""
    identifiers: tuple[tuple[SettingsScope, int | None], ...] = (
        ("organization", organization_id),
        ("site", site_id),
        ("manufacturer", manufacturer_id),
    )
    populated = [name for name, identifier in identifiers if identifier is not None]
    if not populated:
        return "global"
    if len(populated) == 1:
        return populated[0]
    return None


def matches_definition_scope(
    *,
    definition_scope: str,
    organization_id: int | None,
    site_id: int | None,
    manufacturer_id: int | None,
) -> bool:
    """Return whether identifiers match a setting definition's declared scope."""
    return definition_scope == resolve_scope(
        organization_id=organization_id,
        site_id=site_id,
        manufacturer_id=manufacturer_id,
    )
