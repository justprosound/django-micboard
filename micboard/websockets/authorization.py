"""How long one WebSocket connection may act on an authorization decision.

Micboard re-reads a connection's authorized routes from the database before forwarding an
event, so a connection fails closed the moment a membership, a permission, or the account
itself is revoked. Doing that once per frame makes the cost of the guarantee unbounded: a
busy chassis broadcasts many frames per second, and the one inbound command a client may
send takes the same path, so a client sets the pace of the server's database work.

This module puts a declared number on both halves. An authorization decision is reused for
a bounded time to live instead of re-read per frame, which turns revocation latency into a
value a deployment chooses rather than an implicit "every frame". Inbound commands are
metered separately, so no client can force re-reads faster than its own budget allows.

Setting the time to live to zero restores per-frame re-reading for deployments that want
revocation to take effect on the very next frame and can afford the queries.
"""

from __future__ import annotations

import math
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final

from micboard.services.settings.settings_service import settings as micboard_settings

__all__ = [
    "DEFAULT_AUTHORIZATION_TTL_SECONDS",
    "DEFAULT_COMMANDS_PER_MINUTE",
    "MAX_AUTHORIZATION_TTL_SECONDS",
    "MAX_COMMANDS_PER_MINUTE",
    "AuthorizationCache",
    "CommandBudget",
    "authorization_ttl_seconds",
    "command_budget",
]

#: Revocation latency a deployment accepts in exchange for bounded database work. Five
#: seconds is roughly one browser poll cycle, short enough that a revoked viewer sees at
#: most one more burst and long enough to collapse a chassis's broadcast storm into one
#: query.
DEFAULT_AUTHORIZATION_TTL_SECONDS: Final[float] = 5.0
MAX_AUTHORIZATION_TTL_SECONDS: Final[float] = 300.0

#: Inbound commands one connection may spend per minute. The only command Micboard
#: accepts is a keepalive ping, which a well-behaved client sends far below this rate.
DEFAULT_COMMANDS_PER_MINUTE: Final[int] = 60
MAX_COMMANDS_PER_MINUTE: Final[int] = 6000

COMMAND_WINDOW_SECONDS: Final[float] = 60.0


def _finite(value: Any, *, default: float) -> float:
    """Read one host-supplied bound as a finite number.

    These are plain Django settings with no validation in front of them, and the two ways
    they go wrong both defeat clamping rather than being caught by it. `int(float("inf"))`
    raises `OverflowError`, which would fail every handshake; and every comparison against
    NaN is false, so `max(0.0, min(nan, ceiling))` silently collapses to the floor and turns
    the bound off instead of reporting it.

    Args:
        value: Candidate value from host settings.
        default: Value to use when *value* is unusable.

    Returns:
        A finite float, either *value* or *default*.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def authorization_ttl_seconds() -> float:
    """Return how long one authorization decision may be reused.

    Returns:
        A time to live in seconds, clamped to the supported range. Zero means every
        forwarded event re-reads authorization from the database.
    """
    ttl = _finite(
        micboard_settings.get(
            "MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS",
            DEFAULT_AUTHORIZATION_TTL_SECONDS,
        ),
        default=DEFAULT_AUTHORIZATION_TTL_SECONDS,
    )
    return max(0.0, min(ttl, MAX_AUTHORIZATION_TTL_SECONDS))


def commands_per_minute() -> int:
    """Return how many inbound commands one connection may spend per minute.

    Returns:
        A whole number of commands, clamped to the supported range.
    """
    allowance = _finite(
        micboard_settings.get(
            "MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE",
            DEFAULT_COMMANDS_PER_MINUTE,
        ),
        default=DEFAULT_COMMANDS_PER_MINUTE,
    )
    return max(1, min(int(allowance), MAX_COMMANDS_PER_MINUTE))


class AuthorizationCache:
    """Reuse one connection's authorized routes for a bounded time to live."""

    def __init__(
        self,
        *,
        resolve: Callable[[], Awaitable[tuple[str, ...]]],
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Store the resolver whose result this cache is allowed to reuse.

        Args:
            resolve: Coroutine function returning the currently authorized routes.
            ttl_seconds: How long one result may be reused. Zero disables reuse.
            clock: Monotonic time source, overridable for tests.
        """
        self._resolve = resolve
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._groups: tuple[str, ...] | None = None
        self._expires_at = 0.0

    async def authorized_groups(self) -> tuple[str, ...]:
        """Return the connection's authorized routes, re-reading them only when stale.

        Returns:
            Every route the connection is currently allowed to receive events on.
        """
        now = self._clock()
        if self._groups is None or now >= self._expires_at:
            self._groups = await self._resolve()
            self._expires_at = now + self._ttl_seconds
        return self._groups

    def invalidate(self) -> None:
        """Discard the cached decision so the next read goes to the database."""
        self._groups = None
        self._expires_at = 0.0


class CommandBudget:
    """Meter how many inbound commands one connection may spend per window."""

    def __init__(
        self,
        *,
        max_commands: int,
        window_seconds: float = COMMAND_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Start one connection's command allowance.

        Args:
            max_commands: Commands permitted within each window.
            window_seconds: Length of the window in seconds.
            clock: Monotonic time source, overridable for tests.
        """
        self._max_commands = max_commands
        self._window_seconds = window_seconds
        self._clock = clock
        self._window_started_at = clock()
        self._spent = 0

    def consume(self) -> bool:
        """Spend one command from the current window.

        Returns:
            ``True`` when the command is within budget, ``False`` when it is not.
        """
        now = self._clock()
        if now - self._window_started_at >= self._window_seconds:
            self._window_started_at = now
            self._spent = 0
        if self._spent >= self._max_commands:
            return False
        self._spent += 1
        return True

    @property
    def just_exhausted(self) -> bool:
        """Whether the budget has reached its limit exactly once in this window."""
        return self._spent == self._max_commands


def command_budget() -> CommandBudget:
    """Build one connection's command budget from host configuration.

    Returns:
        A budget metering the configured number of commands per minute.
    """
    return CommandBudget(max_commands=commands_per_minute())
