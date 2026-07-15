"""Discovery-trigger policy for persisted registry configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN, MicboardConfig


def discovery_manufacturer_for_config(config: MicboardConfig) -> int | None:
    """Return the manufacturer to rescan after a relevant config change."""
    if config.manufacturer and config.key in (
        "SHURE_DISCOVERY_CIDRS",
        "SHURE_DISCOVERY_FQDNS",
    ):
        return config.manufacturer.pk
    return None


def discovery_manufacturer_for_entry(entry: DiscoveryCIDR | DiscoveryFQDN) -> int:
    """Return the manufacturer to rescan after a registry entry change."""
    return entry.manufacturer_id
