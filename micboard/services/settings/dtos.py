"""Data-transfer objects for tenant-aware settings presentation."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from micboard.services.shared.base_dto import PydanticBaseDTO


class SettingsVisibilityScope(PydanticBaseDTO):
    """Identifiers whose stored overrides a user may inspect.

    ``None`` means unrestricted access for that dimension. An empty set means
    fail closed and expose no overrides for that dimension.
    """

    organization_ids: frozenset[int] | None = None
    site_ids: frozenset[int] | None = None
    manufacturer_ids: frozenset[int] | None = None


class SettingWriteTarget(PydanticBaseDTO):
    """One exact global, organization, site, or manufacturer scope."""

    scope: str
    organization_id: int | None = None
    site_id: int | None = None
    manufacturer_id: int | None = None

    @model_validator(mode="after")
    def validate_exact_scope(self) -> SettingWriteTarget:
        """Reject identifiers that do not match the declared scope."""
        expected = {
            "global": (None, None, None),
            "organization": (self.organization_id, None, None),
            "site": (None, self.site_id, None),
            "manufacturer": (None, None, self.manufacturer_id),
        }
        if self.scope not in expected:
            raise ValueError("Unsupported setting scope")
        actual = (self.organization_id, self.site_id, self.manufacturer_id)
        required = expected[self.scope]
        if actual != required or (self.scope != "global" and all(item is None for item in actual)):
            raise ValueError("Setting target does not match its declared scope")
        return self


class SettingWriteItem(PydanticBaseDTO):
    """One validated form value awaiting definition serialization."""

    value: Any
    definition_id: int | None = None
    key: str | None = None
    label: str = "setting"

    @model_validator(mode="after")
    def validate_identifier(self) -> SettingWriteItem:
        """Require exactly one definition identifier."""
        if (self.definition_id is None) == (self.key is None):
            raise ValueError("Setting write item requires one definition identifier")
        return self


class SettingsWriteRequest(PydanticBaseDTO):
    """Authorized batch of setting override writes."""

    target: SettingWriteTarget
    items: list[SettingWriteItem]


class SettingsWriteResult(PydanticBaseDTO):
    """Best-effort persistence result safe to render to an operator."""

    saved: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
