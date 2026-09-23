"""One module that decides how often each live browser surface re-polls the server.

Micboard delivers every live browser update by short-polling over ordinary HTTP, so the
poll interval multiplied by the number of open tabs is the entire request volume the
deployment's reverse proxy carries. Leaving each interval as a literal in its template put
that number out of a deployer's reach: slowing a busy page down meant forking presentation
markup. This module owns the decision instead, resolving each surface through the same
host-configuration seam the rest of Micboard uses and clamping the result to the bounds
that already govern stored kiosk refresh rates.
"""

from __future__ import annotations

from typing import Any, Final

from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.settings.defaults import (
    DEFAULT_CONFIG,
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
)

__all__ = [
    "BROWSER_REFRESH_SURFACES",
    "MAX_REFRESH_INTERVAL_SECONDS",
    "MIN_REFRESH_INTERVAL_SECONDS",
    "BrowserRefreshCadence",
    "browser_refresh_cadence",
]

#: Every live surface Micboard ships, mapped to the configuration key that tunes it.
#: Surfaces are declared here rather than at a call site so that the set of things a
#: deployer can tune is discoverable in one place.
BROWSER_REFRESH_SURFACES: Final[dict[str, str]] = {
    "alerts": "REFRESH_INTERVAL_ALERTS",
    "assignments": "REFRESH_INTERVAL_ASSIGNMENTS",
    "chargers": "REFRESH_INTERVAL_CHARGERS",
    "kiosk_heartbeat": "REFRESH_INTERVAL_KIOSK_HEARTBEAT",
}


def bounded_refresh_interval(value: Any, *, default: int) -> int:
    """Return one refresh interval clamped into the range a browser can be trusted with.

    Args:
        value: Candidate interval from host configuration or a stored row.
        default: Interval to use when *value* cannot be read as a whole number.

    Returns:
        A whole number of seconds within the shared refresh bounds.
    """
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = default
    return max(MIN_REFRESH_INTERVAL_SECONDS, min(seconds, MAX_REFRESH_INTERVAL_SECONDS))


class BrowserRefreshCadence:
    """Resolve the bounded poll interval for one named browser surface."""

    def seconds_for(self, surface: str) -> int:
        """Return how many seconds *surface* waits between refreshes.

        Args:
            surface: A key of :data:`BROWSER_REFRESH_SURFACES`.

        Returns:
            The configured interval, clamped to the shared refresh bounds.

        Raises:
            ValueError: If *surface* is not a declared browser refresh surface.
        """
        key = BROWSER_REFRESH_SURFACES.get(surface)
        if key is None:
            raise ValueError(f"Unknown browser refresh surface: {surface}")
        configured = micboard_settings.get_config_dict().get(key)
        return bounded_refresh_interval(configured, default=int(DEFAULT_CONFIG[key]))  # type: ignore[arg-type]

    def milliseconds_for(self, surface: str) -> int:
        """Return the same bounded interval as a JavaScript timer duration.

        Args:
            surface: A key of :data:`BROWSER_REFRESH_SURFACES`.

        Returns:
            The configured interval in milliseconds.
        """
        return self.seconds_for(surface) * 1000


browser_refresh_cadence = BrowserRefreshCadence()
