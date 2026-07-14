"""Data Transfer Objects for hardware service layer.

All DTOs inherit from PydanticBaseDTO for consistent configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO


class BandPlanInfo(PydanticBaseDTO):
    """DTO for band plan information."""

    name: str | None = None
    min_mhz: float | None = None
    max_mhz: float | None = None
    source: str | None = None  # 'api', 'model', or None
    message: str | None = None


class ChassisRefreshResult(PydanticBaseDTO):
    """Summary of one tenant-scoped chassis refresh operation."""

    synced_count: int
    failed_count: int
    denied: bool = False
    truncated: bool = False


class ChassisSaveContext(PydanticBaseDTO):
    """Derived state carried between chassis pre-save and post-save adapters."""

    created: bool
    old_status: str | None = None
    status_changed: bool = False
    update_fields: set[str] = Field(default_factory=set)
    discovery_manufacturer_ids: tuple[int, ...] = ()


class WirelessChassisWrite(PydanticBaseDTO):
    """Validated field set for one WirelessChassis persistence operation."""

    manufacturer: Any | None = None
    api_device_id: str | None = None
    ip: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    name: str | None = None
    fqdn: str | None = None
    model: str | None = None
    role: str | None = None
    firmware_version: str | None = None
    hosted_firmware_version: str | None = None
    description: str | None = None
    protocol_family: str | None = None
    wmas_capable: bool | None = None
    licensed_resource_count: int | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    network_mode: str | None = None
    interface_id: str | None = None
    mac_address_secondary: str | None = None
    ip_address_secondary: str | None = None
    location: Any | None = None
    order: int | None = None
    max_channels: int | None = None
    status: str | None = None
    is_online: bool | None = None
    last_seen: datetime | None = None
    last_online_at: datetime | None = None
    last_offline_at: datetime | None = None
    total_uptime_minutes: int | None = None
    dante_capable: bool | None = None
    band_plan_name: str | None = None
    band_plan_min_mhz: float | None = None
    band_plan_max_mhz: float | None = None


class RegulatoryDomainDTO(PydanticBaseDTO):
    """Minimal regulatory-domain projection used by query-optimized displays."""

    code: str
    min_frequency_mhz: float
    max_frequency_mhz: float
