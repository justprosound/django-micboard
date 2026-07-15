"""Typed, bounded charger polling results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from micboard.services.shared.base_dto import PydanticBaseDTO


class ChargerPollingLimits(PydanticBaseDTO):
    """Host-configurable limits constrained by package hard ceilings."""

    max_devices: int = Field(ge=1, le=500)
    max_stations: int = Field(
        ge=1,
        le=256,
        description="Maximum vendor-order station prefix retained in a complete snapshot.",
    )
    max_slots: int = Field(ge=1, le=128)


class ChargerSlotSnapshot(PydanticBaseDTO):
    """One display-safe charger slot snapshot."""

    slot_number: int = Field(ge=0, le=1024)
    mic_name: str = Field(max_length=200)
    battery_level: int = Field(ge=0, le=100)
    charging: bool


class ChargerStationSnapshot(PydanticBaseDTO):
    """One display-safe charger station snapshot."""

    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=200)
    status: Literal["online", "offline"]
    slots: list[ChargerSlotSnapshot] = Field(max_length=128)


class ChargerInventoryPage(PydanticBaseDTO):
    """One deterministic bounded page from a vendor inventory."""

    items: list[dict[str, Any]] = Field(max_length=500)
    start_offset: int = Field(ge=0)
    next_offset: int = Field(ge=0)
    inventory_size: int | None = Field(default=None, ge=0)
    inventory_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    inventory_truncated: bool
    cycle_complete: bool


class ChargerPollingCursor(PydanticBaseDTO):
    """Cache-safe continuation state for a partial charger inventory cycle."""

    next_offset: int = Field(ge=0)
    inventory_size: int = Field(ge=0)
    inventory_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    stations: list[ChargerStationSnapshot] = Field(max_length=256)
    stations_truncated: bool = False
    slots_truncated: bool = False
    cycle_failed: bool = False

    @model_validator(mode="after")
    def require_fingerprint_for_continuation(self) -> ChargerPollingCursor:
        """Reject legacy or corrupt continuation state that cannot bind an inventory."""
        if self.next_offset and self.inventory_fingerprint is None:
            raise ValueError("continued charger polling cursors require an inventory fingerprint")
        return self


class ChargerPollResult(PydanticBaseDTO):
    """Queue-safe outcome of one bounded charger poll."""

    scanned_count: int = Field(ge=0, le=500)
    cached_count: int = Field(ge=0, le=256)
    failed_count: int = Field(ge=0, le=500)
    inventory_truncated: bool = False
    stations_truncated: bool = False
    slots_truncated: bool = False
