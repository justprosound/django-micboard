"""Data-transfer objects for tenant-aware settings presentation."""

from __future__ import annotations

from micboard.services.shared.base_dto import PydanticBaseDTO


class SettingsVisibilityScope(PydanticBaseDTO):
    """Identifiers whose stored overrides a user may inspect.

    ``None`` means unrestricted access for that dimension. An empty set means
    fail closed and expose no overrides for that dimension.
    """

    organization_ids: frozenset[int] | None = None
    site_ids: frozenset[int] | None = None
    manufacturer_ids: frozenset[int] | None = None
