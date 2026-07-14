"""Data Transfer Objects for hardware service layer.

All DTOs inherit from PydanticBaseDTO for consistent configuration.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from micboard.services.shared.base_dto import PydanticBaseDTO


class ChassisStatus(StrEnum):
    """Wireless chassis status values."""

    ONLINE = "online"
    DEGRADED = "degraded"
    PROVISIONING = "provisioning"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class AccessoryTypeDTO(PydanticBaseDTO):
    """DTO for accessory type information."""

    category: str
    total: int
    unavailable: int
    needs_repair: int


class BandPlanInfo(PydanticBaseDTO):
    """DTO for band plan information."""

    name: str | None = None
    min_mhz: float | None = None
    max_mhz: float | None = None
    source: str | None = None  # 'api', 'model', or None
    message: str | None = None


class WirelessChassisDTO(PydanticBaseDTO):
    """DTO for WirelessChassis data transfer."""

    id: int
    name: str
    model: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    ip_address: str | None = None
    status: ChassisStatus
    is_active: bool
    last_polled: datetime | None = None
    band_plan: BandPlanInfo | None = None
    accessory_count: int = 0
    has_accessories: bool = False


class GapAnalysisDTO(PydanticBaseDTO):
    """DTO for gap analysis data."""

    title: str
    total_chassis: int
    missing_fields: dict[str, int]
    missing_fields_pct: dict[str, float]
    chassis_without_accessories: int
    accessories_by_type: list[AccessoryTypeDTO]
    devices_by_model_with_gaps: list[dict[str, Any]]
    last_polled_gap: int
    needs_attention: dict[str, int]


class ChassisBandPlanUpdate(PydanticBaseDTO):
    """DTO for updating chassis band plan information."""

    band_plan_name: str | None = None
    band_plan_min_mhz: float | None = None
    band_plan_max_mhz: float | None = None


class ChassisDiscoveryCleanup(PydanticBaseDTO):
    """Manufacturer discovery cleanup snapshot requested by chassis deletion."""

    manufacturer_id: int
    ip: str


class ChassisRefreshResult(PydanticBaseDTO):
    """Summary of one tenant-scoped chassis refresh operation."""

    synced_count: int
    failed_count: int
