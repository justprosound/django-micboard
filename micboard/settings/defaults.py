"""Dependency-free defaults for the Micboard settings interface."""

from __future__ import annotations

from typing import Final

#: Bounds shared by every browser refresh interval, whether it comes from host
#: configuration or from a stored ``DisplayWall`` row. Below the floor a browser polls as
#: fast as it can issue requests; above the ceiling the timer is effectively off, which
#: hides staleness from operators rather than reducing load.
MIN_REFRESH_INTERVAL_SECONDS: Final[int] = 2
MAX_REFRESH_INTERVAL_SECONDS: Final[int] = 3600

DEFAULT_CONFIG: Final[dict[str, str | int | float | bool | list[int] | None]] = {
    "POLL_INTERVAL": 5,
    "CACHE_TIMEOUT": 30,
    "TRANSMITTER_INACTIVITY_SECONDS": 10,
    # How often each live browser surface re-polls. Poll interval multiplied by open tabs
    # is the whole request volume Micboard puts through a deployment's reverse proxy, so
    # these are host-tunable rather than fixed in markup.
    "REFRESH_INTERVAL_ALERTS": 5,
    "REFRESH_INTERVAL_ASSIGNMENTS": 5,
    "REFRESH_INTERVAL_CHARGERS": 10,
    "REFRESH_INTERVAL_KIOSK_HEARTBEAT": 30,
}
