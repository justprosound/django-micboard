"""Typed projections for wireless-chassis admin views."""

from __future__ import annotations

from micboard.services.shared.base_dto import PydanticBaseDTO


class HardwareLayoutChannel(PydanticBaseDTO):
    """One RF channel in the active hardware layout."""

    channel_number: int
    frequency: str | None


class HardwareLayoutChassis(PydanticBaseDTO):
    """One chassis and its ordered RF channels."""

    id: int
    name: str
    ip_address: str
    channels: list[HardwareLayoutChannel]


class HardwareLayoutLocation(PydanticBaseDTO):
    """Chassis grouped under one network location label."""

    name: str
    chassis: list[HardwareLayoutChassis]


class HardwareLayoutManufacturer(PydanticBaseDTO):
    """Locations grouped under one manufacturer."""

    name: str
    locations: list[HardwareLayoutLocation]


class HardwareLayoutPage(PydanticBaseDTO):
    """Complete bounded projection for the hardware-layout admin page."""

    manufacturers: list[HardwareLayoutManufacturer]


class HardwareSummaryChannel(PydanticBaseDTO):
    """One channel in a chassis readonly summary."""

    channel_number: int
    unit_type: str | None
