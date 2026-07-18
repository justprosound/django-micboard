"""Data-transfer objects for Django admin configuration audits."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, computed_field, field_validator

from micboard.services.shared.base_dto import PydanticBaseDTO

AuditSeverity = Literal["info", "warning", "error"]
MAX_ADMIN_AUDIT_THREADS = 32


class AdminAuditOptions(PydanticBaseDTO):
    """Validated filters and check selection for an admin audit."""

    app_label: str | None = None
    model_names: tuple[str, ...] = ()
    excluded_names: tuple[str, ...] = ()
    errors_only: bool = False
    quick: bool = False
    check_n1: bool = False
    check_unfold: bool = False
    check_media: bool = False
    check_search_depth: bool = False
    threads: int = Field(default=1, ge=1, le=MAX_ADMIN_AUDIT_THREADS)

    @field_validator("model_names", "excluded_names", mode="before")
    @classmethod
    def normalize_names(cls, value: object) -> tuple[str, ...]:
        """Normalize optional argparse lists into immutable name collections."""
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list | tuple | set | frozenset):
            return tuple(str(item) for item in value)
        raise ValueError("model filters must be strings or collections of strings")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_check_filter(self) -> bool:
        """Return whether the caller selected one or more check categories."""
        return any(
            (
                self.check_n1,
                self.check_unfold,
                self.check_media,
                self.check_search_depth,
            )
        )


class AdminAuditMessage(PydanticBaseDTO):
    """One human-readable audit finding."""

    text: str
    severity: AuditSeverity = "info"


class AdminAuditStats(PydanticBaseDTO):
    """Stable counters emitted by the admin audit."""

    models_scanned: int = 0
    n_plus_one_warnings: int = 0
    n_plus_one_fails: int = 0
    unfold_compliant: int = 0
    unfold_non_compliant: int = 0
    widgets_optimized: int = 0
    filters_optimized: int = 0
    search_warnings: int = 0
    template_errors: int = 0
    media_warnings: int = 0

    @classmethod
    def from_mapping(cls, values: Mapping[str, int]) -> AdminAuditStats:
        """Build typed counters from an internal aggregation mapping."""
        return cls(**{name: values.get(name, 0) for name in cls.model_fields})


class AdminModelAuditResult(PydanticBaseDTO):
    """Findings and counters for one registered model."""

    app_label: str
    model_name: str
    messages: tuple[AdminAuditMessage, ...] = ()
    stats: AdminAuditStats = Field(default_factory=AdminAuditStats)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_issues(self) -> bool:
        """Return whether this model emitted a warning or error."""
        return any(message.severity != "info" for message in self.messages)


class AdminAuditReport(PydanticBaseDTO):
    """Complete audit output returned to the management command."""

    messages: tuple[AdminAuditMessage, ...] = ()
    stats: AdminAuditStats = Field(default_factory=AdminAuditStats)
    matched_models: int = 0
