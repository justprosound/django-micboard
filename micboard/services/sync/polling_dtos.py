"""Validated limits and results for manufacturer polling."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import islice
from typing import Any

from django.conf import settings

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

DEFAULT_MAX_POLL_DEVICES = 500
HARD_MAX_POLL_DEVICES = 5_000
DEFAULT_BROADCAST_CHUNK_SIZE = 100
HARD_MAX_BROADCAST_CHUNK_SIZE = 500


class ManufacturerPollLimits(PydanticBaseDTO):
    """Host-configured polling limits constrained by package hard ceilings."""

    max_devices: int = Field(ge=1, le=HARD_MAX_POLL_DEVICES)
    broadcast_chunk_size: int = Field(ge=1, le=HARD_MAX_BROADCAST_CHUNK_SIZE)

    @classmethod
    def from_settings(cls) -> ManufacturerPollLimits:
        """Resolve safe limits from Django settings."""
        return cls(
            max_devices=_bounded_positive_setting(
                "MICBOARD_POLL_MAX_DEVICES",
                default=DEFAULT_MAX_POLL_DEVICES,
                hard_limit=HARD_MAX_POLL_DEVICES,
            ),
            broadcast_chunk_size=_bounded_positive_setting(
                "MICBOARD_POLL_BROADCAST_CHUNK_SIZE",
                default=DEFAULT_BROADCAST_CHUNK_SIZE,
                hard_limit=HARD_MAX_BROADCAST_CHUNK_SIZE,
            ),
        )


class VendorInventoryBatch(PydanticBaseDTO):
    """A bounded prefix of one manufacturer inventory response."""

    devices: tuple[dict[str, Any], ...] = Field(max_length=HARD_MAX_POLL_DEVICES + 1)
    device_limit: int = Field(ge=1, le=HARD_MAX_POLL_DEVICES)

    @property
    def inventory_complete(self) -> bool:
        """Return whether the source ended within the configured limit."""
        return len(self.devices) <= self.device_limit

    @classmethod
    def consume(
        cls,
        devices: Iterable[dict[str, Any]],
        *,
        device_limit: int,
    ) -> VendorInventoryBatch:
        """Consume at most ``device_limit + 1`` items to detect overflow."""
        bounded_devices = tuple(islice(devices, device_limit + 1))
        return cls(devices=bounded_devices, device_limit=device_limit)


class ManufacturerSyncResult(PydanticBaseDTO):
    """Serializable outcome for one bounded manufacturer inventory sync."""

    success: bool
    devices_added: int = Field(default=0, ge=0)
    devices_updated: int = Field(default=0, ge=0)
    devices_removed: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
    devices_examined: int = Field(default=0, ge=0, le=HARD_MAX_POLL_DEVICES + 1)
    device_limit: int = Field(ge=1, le=HARD_MAX_POLL_DEVICES)
    inventory_complete: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return the stable mapping consumed by existing task and service APIs."""
        return self.model_dump(mode="python")


def _bounded_positive_setting(name: str, *, default: int, hard_limit: int) -> int:
    """Parse a positive integer setting and enforce a package hard ceiling."""
    raw_value = getattr(settings, name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed_value, 1), hard_limit)
