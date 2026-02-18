"""Device specifications service for centralized spec lookups.

Provides a clean interface for accessing device specifications from the registry
without embedding lookup logic in models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


@dataclass
class DeviceSpec:
    """Device specifications from registry."""

    max_channels: int
    dante_capable: bool
    model: str
    manufacturer: str

    def __repr__(self) -> str:
        return f"DeviceSpec({self.model}, channels={self.max_channels}, dante={self.dante_capable})"


class DeviceSpecService:
    """Service for looking up standardized device specifications."""

    @staticmethod
    def get_specs(manufacturer: Manufacturer | None, model: str) -> DeviceSpec | None:
        """Get device specifications for a manufacturer/model combination.

        Args:
            manufacturer: Manufacturer instance (can be None).
            model: Device model name/code.

        Returns:
            DeviceSpec instance with specs, or None if not found.
        """
        if not manufacturer or not model:
            return None

        from micboard.models.device_specs import (
            get_channel_count,
            get_dante_support,
        )

        try:
            mfg_code = manufacturer.code.lower() if hasattr(manufacturer, "code") else ""

            max_channels = get_channel_count(
                manufacturer=mfg_code,
                model=model,
            )
            dante_capable = get_dante_support(
                manufacturer=mfg_code,
                model=model,
            )

            return DeviceSpec(
                max_channels=max_channels,
                dante_capable=dante_capable,
                model=model,
                manufacturer=mfg_code,
            )
        except Exception as e:
            logger.warning(f"Failed to get specs for {manufacturer.code}/{model}: {e}")
            return None

    @staticmethod
    def apply_specs_to_chassis(chassis: object) -> None:
        """Apply specifications to a WirelessChassis instance (for use in save()).

        Args:
            chassis: WirelessChassis instance with manufacturer and model set.
        """
        spec = DeviceSpecService.get_specs(
            getattr(chassis, "manufacturer", None),
            getattr(chassis, "model", ""),
        )

        if spec:
            chassis.max_channels = spec.max_channels  # type: ignore
            chassis.dante_capable = spec.dante_capable  # type: ignore
            logger.debug(f"Applied specs to {chassis}: {spec}")
