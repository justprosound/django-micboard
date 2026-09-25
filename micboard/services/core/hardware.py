"""Manufacturer-neutral shape of one polled or streamed chassis.

Every integration's normalizer returns a `NormalizedChassis`, and every persistence path
reads it. Vendor key names stop at the normalizer, so callers read fields rather than
guessing which spelling a payload used.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.utils.mac_address import canonicalize_mac_address

UNKNOWN_BYTE_LEVEL = 255
"""Vendor sentinel for a battery, quality, or offset reading the device did not report."""


class NormalizedUnit(PydanticBaseDTO):
    """Telemetry for the wireless unit linked to one RF channel."""

    slot: int | None = None
    battery: int = UNKNOWN_BYTE_LEVEL
    battery_charge: int | None = None
    battery_type: str = ""
    runtime: str = ""
    battery_health: str = ""
    battery_cycles: int | None = None
    battery_temperature_c: float | None = None
    audio_level: int = 0
    rf_level: int = 0
    frequency: str = ""
    antenna: str = ""
    tx_offset: int = UNKNOWN_BYTE_LEVEL
    quality: int = UNKNOWN_BYTE_LEVEL
    status: str = ""
    name: str = ""


class NormalizedChannel(PydanticBaseDTO):
    """One RF channel reported by a chassis, with its linked unit if any."""

    number: int
    unit: NormalizedUnit | None = None


class NormalizedChassis(PydanticBaseDTO):
    """One chassis as reported by its manufacturer, independent of vendor key names.

    `model` is the full model number the vendor reported (for example ``ULXD4Q``), or empty
    when the payload names none; persistence never overwrites a known model with an empty one.
    `role` is set only when the device specification recognizes that model, and persistence keeps
    the existing role otherwise.
    `channels` is empty when the payload embedded no channel list.
    """

    api_device_id: str = Field(min_length=1)
    ip: str = ""
    serial_number: str = ""
    mac_address: str = ""
    name: str = ""
    model: str = ""
    role: str | None = None
    firmware_version: str = ""
    hosted_firmware_version: str = ""
    description: str = ""
    subnet_mask: str | None = None
    gateway: str | None = None
    network_mode: str = "auto"
    interface_id: str = ""
    channels: list[NormalizedChannel] = Field(default_factory=list)

    @field_validator("mac_address", mode="before")
    @classmethod
    def canonicalize_mac(cls, value: Any) -> str:
        """Canonicalize hardware identity on creation and assignment."""
        return canonicalize_mac_address(value if isinstance(value, str) else None) or ""
