"""What a WebSocket connection is allowed to spend to stay authorized.

Forwarding an event used to re-read the connection's authorized routes from the database
every single time, which is correct but costs an unbounded number of queries: broadcasts
arrive as fast as hardware changes, and the one inbound command a client may send took the
same path. These tests pin the two numbers that now bound it — how long one authorization
decision may be reused, and how many commands one connection may spend per minute.
"""

from __future__ import annotations

import asyncio

from django.test import override_settings

import pytest

from micboard.websockets.authorization import (
    DEFAULT_AUTHORIZATION_TTL_SECONDS,
    DEFAULT_COMMANDS_PER_MINUTE,
    MAX_AUTHORIZATION_TTL_SECONDS,
    MAX_COMMANDS_PER_MINUTE,
    AuthorizationCache,
    CommandBudget,
    authorization_ttl_seconds,
    commands_per_minute,
)


class FakeClock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += seconds


def _counting_resolver(results: list[tuple[str, ...]]) -> tuple[object, list[int]]:
    """Build a resolver that yields each queued result once and counts its calls."""
    calls: list[int] = []

    async def resolve() -> tuple[str, ...]:
        calls.append(1)
        return results[min(len(calls) - 1, len(results) - 1)]

    return resolve, calls


def test_a_burst_of_events_costs_one_authorization_read() -> None:
    """The whole point: many frames inside one time to live share one database read."""
    clock = FakeClock()
    resolve, calls = _counting_resolver([("group",)])
    cache = AuthorizationCache(resolve=resolve, ttl_seconds=5.0, clock=clock)

    for _ in range(50):
        assert asyncio.run(cache.authorized_groups()) == ("group",)

    assert len(calls) == 1


def test_a_decision_is_re_read_once_its_time_to_live_expires() -> None:
    """Reuse is bounded, so a revocation lands no later than one time to live later."""
    clock = FakeClock()
    resolve, calls = _counting_resolver([("group",), ()])
    cache = AuthorizationCache(resolve=resolve, ttl_seconds=5.0, clock=clock)

    assert asyncio.run(cache.authorized_groups()) == ("group",)
    clock.advance(5.0)
    assert asyncio.run(cache.authorized_groups()) == ()
    assert len(calls) == 2


def test_a_zero_time_to_live_restores_per_event_re_reading() -> None:
    """A deployment that cannot accept any revocation latency can opt back in."""
    clock = FakeClock()
    resolve, calls = _counting_resolver([("group",)])
    cache = AuthorizationCache(resolve=resolve, ttl_seconds=0.0, clock=clock)

    asyncio.run(cache.authorized_groups())
    asyncio.run(cache.authorized_groups())

    assert len(calls) == 2


def test_invalidating_a_decision_sends_the_next_read_to_the_database() -> None:
    """Closing a revoked connection must not leave a stale decision behind it."""
    clock = FakeClock()
    resolve, calls = _counting_resolver([("group",)])
    cache = AuthorizationCache(resolve=resolve, ttl_seconds=300.0, clock=clock)

    asyncio.run(cache.authorized_groups())
    cache.invalidate()
    asyncio.run(cache.authorized_groups())

    assert len(calls) == 2


def test_commands_beyond_the_budget_are_refused() -> None:
    """A client cannot pace the server's work faster than its own allowance."""
    clock = FakeClock()
    budget = CommandBudget(max_commands=3, window_seconds=60.0, clock=clock)

    assert [budget.consume() for _ in range(5)] == [True, True, True, False, False]


def test_the_budget_refills_when_its_window_rolls_over() -> None:
    """The bound is a rate, not a lifetime quota, so a quiet client is never locked out."""
    clock = FakeClock()
    budget = CommandBudget(max_commands=2, window_seconds=60.0, clock=clock)

    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False
    clock.advance(60.0)
    assert budget.consume() is True


def test_defaults_apply_when_a_host_configures_nothing() -> None:
    """Micboard ships bounded, not unbounded, without any host configuration."""
    assert authorization_ttl_seconds() == DEFAULT_AUTHORIZATION_TTL_SECONDS
    assert commands_per_minute() == DEFAULT_COMMANDS_PER_MINUTE


@override_settings(
    MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS=30,
    MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE=10,
)
def test_a_host_chooses_its_own_revocation_latency_and_command_rate() -> None:
    """Both numbers are declared settings rather than constants buried in the consumer."""
    assert authorization_ttl_seconds() == 30.0
    assert commands_per_minute() == 10


@override_settings(
    MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS=10_000,
    MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE=10_000_000,
)
def test_configured_bounds_cannot_be_raised_past_what_micboard_supports() -> None:
    """An hours-long time to live is indistinguishable from never revoking at all."""
    assert authorization_ttl_seconds() == MAX_AUTHORIZATION_TTL_SECONDS
    assert commands_per_minute() == MAX_COMMANDS_PER_MINUTE


@override_settings(
    MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS="not a number",
    MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE="not a number",
)
def test_an_unusable_value_falls_back_to_the_shipped_default() -> None:
    """A typo in host settings must not disable the bound it was trying to set."""
    assert authorization_ttl_seconds() == DEFAULT_AUTHORIZATION_TTL_SECONDS
    assert commands_per_minute() == DEFAULT_COMMANDS_PER_MINUTE


@override_settings(MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE=0)
def test_a_zero_command_allowance_still_admits_one_command() -> None:
    """Refusing every command would break keepalives rather than bound them."""
    assert commands_per_minute() == 1


@pytest.mark.parametrize("ttl", [-1, -0.5])
def test_a_negative_time_to_live_is_read_as_no_reuse(ttl: float) -> None:
    """Negative reuse has no meaning; the safe reading is per-event re-checking."""
    with override_settings(MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS=ttl):
        assert authorization_ttl_seconds() == 0.0


@override_settings(MICBOARD_WEBSOCKET_COMMANDS_PER_MINUTE=float("inf"))
def test_a_non_finite_command_allowance_falls_back_instead_of_raising() -> None:
    """`int(float("inf"))` raises `OverflowError`, which would break every connection.

    These are host-supplied Django settings with no validation in front of them, so an
    unusable value has to leave the bound at its shipped default rather than fail the
    handshake for everyone.
    """
    assert commands_per_minute() == DEFAULT_COMMANDS_PER_MINUTE


@override_settings(MICBOARD_WEBSOCKET_AUTHORIZATION_TTL_SECONDS=float("nan"))
def test_a_nan_time_to_live_falls_back_to_the_shipped_default() -> None:
    """Clamping a NaN silently turns the bound off rather than reporting it.

    `max(0.0, min(nan, 300.0))` evaluates to `0.0`, because every comparison against NaN is
    false. That is fail-safe — zero means re-read on every frame — but it also means a typo
    quietly restores the unbounded per-frame queries this setting exists to bound.
    """
    assert authorization_ttl_seconds() == DEFAULT_AUTHORIZATION_TTL_SECONDS
