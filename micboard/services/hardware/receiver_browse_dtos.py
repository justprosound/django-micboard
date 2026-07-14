"""Typed projections for tenant-scoped chassis browsing."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO


class ReceiverBrowseCriteria(PydanticBaseDTO):
    """Validated filters for one receiver-browse request."""

    title: str
    manufacturer_code: str | None = None
    role: str | None = None
    building_id: int | None = None
    room_id: int | None = None
    priority: str | None = None
    performer_id: int | None = None


class ReceiverBrowseItem(PydanticBaseDTO):
    """One chassis card safe to expose on the receiver browser."""

    id: int
    name: str
    manufacturer_name: str
    model_name: str
    role: str
    role_label: str
    status: str
    status_label: str
    ip_address: str
    building_name: str | None
    room_name: str | None


class ReceiverBrowsePage(PydanticBaseDTO):
    """Bounded page of receiver cards and navigation metadata."""

    title: str
    items: list[ReceiverBrowseItem]
    total_count: int = Field(ge=0)
    page_number: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    has_previous: bool
    has_next: bool
    previous_page: int | None
    next_page: int | None
    query_string: str
