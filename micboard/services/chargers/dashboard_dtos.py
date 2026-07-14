"""Typed charger-dashboard projections."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

MAX_DASHBOARD_CHARGERS = 64
MAX_DASHBOARD_SLOTS_PER_CHARGER = 32


class ChargerDashboardPerformerSnapshot(PydanticBaseDTO):
    """Performer identity shown for one docked wireless unit."""

    name: str
    title: str
    photo_url: str | None


class ChargerDashboardSlotSnapshot(PydanticBaseDTO):
    """Primitive display state for one charger slot."""

    slot_number: int = Field(ge=1)
    occupied: bool
    device_serial: str
    device_model: str
    battery_percent: int | None
    device_firmware_version: str
    device_status: str
    is_functional: bool
    performer: ChargerDashboardPerformerSnapshot | None = None


class ChargerDashboardChargerSnapshot(PydanticBaseDTO):
    """Primitive display state for one charger and its ordered slots."""

    id: int
    name: str
    model_name: str
    ip_address: str | None
    slots: list[ChargerDashboardSlotSnapshot]
    slots_truncated: bool = False
    slot_limit: int = Field(default=MAX_DASHBOARD_SLOTS_PER_CHARGER, ge=1)


class ChargerDashboardSnapshot(PydanticBaseDTO):
    """Complete tenant-scoped charger grid projection."""

    chargers: list[ChargerDashboardChargerSnapshot]
    chargers_truncated: bool = False
    charger_limit: int = Field(default=MAX_DASHBOARD_CHARGERS, ge=1)
