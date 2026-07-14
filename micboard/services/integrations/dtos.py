"""Data transfer objects for integration services."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO


class APIServerHealthCheckBatchResult(PydanticBaseDTO):
    """Outcome of one permission-checked, bounded API server health-check batch."""

    requested: int = Field(ge=0)
    checked: int = Field(ge=0)
    failed: int = Field(ge=0)
    missing: int = Field(ge=0)
    denied: bool = False
    truncated: bool = False
