"""Public data-transfer objects for manufacturer API health summaries."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from micboard.services.shared.base_dto import PydanticBaseDTO

ManufacturerHealthStatus = Literal[
    "healthy",
    "unhealthy",
    "degraded",
    "offline",
    "error",
    "unknown",
]
AggregateHealthStatus = Literal["healthy", "unhealthy", "partial", "unknown", "unconfigured"]

PUBLIC_API_HEALTH_ERROR = "API health check failed; details redacted."
MAX_PUBLIC_API_HEALTH_MANUFACTURERS = 100


class PublicAPIHealthSnapshot(PydanticBaseDTO):
    """Bounded, secret-safe fields exposed for one manufacturer health check."""

    status: ManufacturerHealthStatus
    response_time: float | None = Field(default=None, ge=0)
    error: str | None = None

    @field_validator("error", mode="before")
    @classmethod
    def redact_error(cls, value: object) -> str | None:
        """Replace producer-supplied error text with a stable public message."""
        return PUBLIC_API_HEALTH_ERROR if value else None


class ManufacturerAPIHealthSnapshot(PydanticBaseDTO):
    """Public health state for one configured manufacturer."""

    manufacturer: str
    code: str
    status: ManufacturerHealthStatus
    details: PublicAPIHealthSnapshot


class APIHealthSummary(PydanticBaseDTO):
    """Bounded aggregate consumed by the public base template."""

    status: AggregateHealthStatus
    details: list[ManufacturerAPIHealthSnapshot] = Field(
        default_factory=list,
        max_length=MAX_PUBLIC_API_HEALTH_MANUFACTURERS,
    )
    total_manufacturers: int = Field(ge=0, le=MAX_PUBLIC_API_HEALTH_MANUFACTURERS)
    healthy_manufacturers: int = Field(ge=0, le=MAX_PUBLIC_API_HEALTH_MANUFACTURERS)
    truncated: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> APIHealthSummary:
        """Reject inconsistent or attacker-controlled aggregate cache metadata."""
        if self.total_manufacturers != len(self.details):
            raise ValueError("total_manufacturers must match bounded details")
        if self.healthy_manufacturers > self.total_manufacturers:
            raise ValueError("healthy_manufacturers cannot exceed total_manufacturers")
        return self
