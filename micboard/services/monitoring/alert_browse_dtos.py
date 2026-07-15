"""Typed projections for alert-history browsing."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO


class AlertBrowseCriteria(PydanticBaseDTO):
    """Validated filters for one alert-history page."""

    status: str = "pending"
    alert_type: str = ""
    page: int | str | None = 1


class AlertBrowseItem(PydanticBaseDTO):
    """One alert row rendered by the page and live fragment."""

    id: int
    created_at: datetime
    alert_type_label: str
    channel_label: str
    performer_name: str | None
    user_display_name: str
    status: str
    status_label: str
    message_preview: str
    message_is_truncated: bool
    is_overdue: bool


class AlertBrowsePage(PydanticBaseDTO):
    """Bounded alert rows plus page navigation metadata."""

    items: list[AlertBrowseItem]
    total_count: int = Field(ge=0)
    page_number: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    page_numbers: list[int]
    has_previous: bool
    has_next: bool
    previous_page: int | None
    next_page: int | None
    status_filter: str
    alert_type_filter: str
    poll_query_string: str


class AlertBrowseRows(PydanticBaseDTO):
    """Count-free alert rows rendered by the live fragment."""

    items: list[AlertBrowseItem]
    page_number: int = Field(ge=1)
    has_next: bool


class AlertBrowseStats(PydanticBaseDTO):
    """Status totals displayed only by the full alert page."""

    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    acknowledged: int = Field(ge=0)
    resolved: int = Field(ge=0)
    failed: int = Field(ge=0)
