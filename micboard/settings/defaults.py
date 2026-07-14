"""Dependency-free defaults for the Micboard settings interface."""

from __future__ import annotations

from typing import Final

DEFAULT_CONFIG: Final[dict[str, str | int | float | bool | list[int] | None]] = {
    "POLL_INTERVAL": 5,
    "CACHE_TIMEOUT": 30,
    "TRANSMITTER_INACTIVITY_SECONDS": 10,
}
