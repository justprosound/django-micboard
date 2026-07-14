"""Regression coverage for bounded realtime subscription supervision."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from django.core.cache import caches
from django.test import override_settings

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime import subscription_supervisor as supervisor_module
from micboard.services.realtime.subscription_dtos import (
    DEFAULT_MAX_SUBSCRIPTION_CONCURRENCY,
    DEFAULT_MAX_SUBSCRIPTION_DEVICES,
    DEFAULT_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
    DEFAULT_SUBSCRIPTION_ROTATION_SECONDS,
    HARD_MAX_SUBSCRIPTION_CONCURRENCY,
    HARD_MAX_SUBSCRIPTION_DEVICES,
    HARD_MAX_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
    HARD_MAX_SUBSCRIPTION_ROTATION_SECONDS,
    SubscriptionLimits,
    SubscriptionSelectionCursor,
)
from micboard.services.realtime.subscription_supervisor import (
    RealtimeSubscriptionLease,
    RealtimeSubscriptionSupervisor,
    SubscriptionLeaseLostError,
    build_device_https_url,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def test_supervisor_lease_deduplicates_until_expiry() -> None:
    """Only one worker can own a transport scope during a lease window."""
    scope = f"test-{uuid4()}"
    first = RealtimeSubscriptionSupervisor.acquire(transport="sse", scope=scope)

    assert first is not None
    assert RealtimeSubscriptionSupervisor.acquire(transport="sse", scope=scope) is None

    first.cache.delete(first.cache_key)
    replacement = RealtimeSubscriptionSupervisor.acquire(transport="sse", scope=scope)
    assert replacement is not None
    replacement.cache.delete(replacement.cache_key)


def test_stale_lease_cannot_refresh_or_delete_replacement_token() -> None:
    """Generic-cache leases expose no unsafe get-then-delete release operation."""
    scope = f"test-{uuid4()}"
    lease = RealtimeSubscriptionSupervisor.acquire(transport="websocket", scope=scope)
    assert lease is not None

    lease.cache.set(lease.cache_key, "replacement", timeout=120)

    assert lease.refresh() is False
    assert not hasattr(lease, "release")
    assert lease.cache.get(lease.cache_key) == "replacement"
    lease.cache.delete(lease.cache_key)


def test_lease_cache_failures_redact_backend_details(caplog) -> None:
    """Cache errors retain their category without logging backend secrets."""
    secret = "private-cache-credential"
    cache = Mock()
    cache.get.side_effect = RuntimeError(secret)
    lease = RealtimeSubscriptionLease(cache=cache, cache_key="scope", token="owner")

    assert lease.refresh() is False
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_lease_refresh_requires_touch_and_post_touch_ownership() -> None:
    """A refresh succeeds only when ownership remains stable through renewal."""
    cache = Mock()
    cache.get.side_effect = ["owner", "owner"]
    cache.touch.return_value = True
    lease = RealtimeSubscriptionLease(cache=cache, cache_key="scope", token="owner")

    assert lease.refresh() is True

    cache.get.side_effect = ["owner"]
    cache.touch.return_value = False
    assert lease.refresh() is False


@override_settings(MICBOARD_REALTIME_CACHE_ALIAS="missing-realtime-cache")
def test_lease_acquisition_fails_closed_for_cache_errors(caplog) -> None:
    """A missing shared cache cannot silently admit duplicate supervisors."""
    assert RealtimeSubscriptionSupervisor.acquire(transport="sse", scope=1) is None
    assert "Failed to acquire" in caplog.text


@override_settings(
    MICBOARD_REALTIME_MAX_DEVICES=100_000,
    MICBOARD_REALTIME_MAX_CONCURRENCY=100_000,
    MICBOARD_REALTIME_ROTATION_SECONDS=100_000,
    MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS=100_000,
)
def test_configured_limits_cannot_exceed_hard_caps() -> None:
    """Host settings cannot disable package workload ceilings."""
    limits = RealtimeSubscriptionSupervisor.limits()

    assert limits.max_devices == HARD_MAX_SUBSCRIPTION_DEVICES
    assert limits.max_concurrency == HARD_MAX_SUBSCRIPTION_CONCURRENCY
    assert limits.rotation_seconds == HARD_MAX_SUBSCRIPTION_ROTATION_SECONDS
    assert limits.reconnect_delay_seconds == HARD_MAX_SUBSCRIPTION_RECONNECT_DELAY_SECONDS


@override_settings(
    MICBOARD_REALTIME_MAX_DEVICES=True,
    MICBOARD_REALTIME_MAX_CONCURRENCY="invalid",
    MICBOARD_REALTIME_ROTATION_SECONDS=float("inf"),
    MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS=False,
)
def test_invalid_limit_settings_use_safe_defaults() -> None:
    """Boolean, malformed, and non-finite settings cannot disable workload bounds."""
    limits = RealtimeSubscriptionSupervisor.limits()

    assert limits.max_devices == DEFAULT_MAX_SUBSCRIPTION_DEVICES
    assert limits.max_concurrency == DEFAULT_MAX_SUBSCRIPTION_CONCURRENCY
    assert limits.rotation_seconds == DEFAULT_SUBSCRIPTION_ROTATION_SECONDS
    assert limits.reconnect_delay_seconds == DEFAULT_SUBSCRIPTION_RECONNECT_DELAY_SECONDS


@pytest.mark.django_db
def test_selection_cursor_rotates_bounded_windows_across_runs(
    django_assert_num_queries,
) -> None:
    """Stable inventory ordering cannot permanently starve rows after the first window."""
    manufacturer = ManufacturerFactory(code=f"fair-{uuid4().hex[:8]}")
    chassis = [
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=f"device-{index}",
            status="online",
        )
        for index in range(5)
    ]
    transport = f"sse-test-{uuid4()}"
    cursor_key = RealtimeSubscriptionSupervisor._selection_cursor_key(
        transport=transport,
        scope=manufacturer.pk,
    )
    caches["default"].delete(cursor_key)
    queryset = manufacturer.wirelesschassis_set.filter(status="online")

    with django_assert_num_queries(1):
        first = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=queryset,
            transport=transport,
            scope=manufacturer.pk,
            limit=2,
        )
    with django_assert_num_queries(1):
        second = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=queryset,
            transport=transport,
            scope=manufacturer.pk,
            limit=2,
        )
    with django_assert_num_queries(2):
        third = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=queryset,
            transport=transport,
            scope=manufacturer.pk,
            limit=2,
        )

    assert [item.pk for item in first] == [chassis[0].pk, chassis[1].pk]
    assert [item.pk for item in second] == [chassis[2].pk, chassis[3].pk]
    assert [item.pk for item in third] == [chassis[4].pk, chassis[0].pk]
    caches["default"].delete(cursor_key)


@pytest.mark.django_db
def test_selection_returns_empty_bounded_window_for_empty_inventory() -> None:
    """An empty queryset performs no cursor write and returns without synthetic work."""
    manufacturer = ManufacturerFactory(code=f"empty-{uuid4().hex[:8]}")
    selected = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
        queryset=manufacturer.wirelesschassis_set.all(),
        transport=f"empty-{uuid4()}",
        scope=manufacturer.pk,
        limit=0,
    )

    assert selected == []


def test_selection_cursor_cache_failures_are_safe_and_redacted(monkeypatch, caplog) -> None:
    """Cursor cache outages fall back to the first window without leaking backend details."""
    secret = "redis://private-realtime-credential"
    cache = Mock()
    cache.get.side_effect = RuntimeError(secret)
    cache.set.side_effect = RuntimeError(secret)
    cache_handler = MagicMock()
    cache_handler.__getitem__.return_value = cache
    monkeypatch.setattr(supervisor_module, "caches", cache_handler)

    cursor = RealtimeSubscriptionSupervisor._read_selection_cursor("cursor")
    RealtimeSubscriptionSupervisor._write_selection_cursor(
        "cursor",
        SubscriptionSelectionCursor(after_id=1),
    )

    assert cursor.after_id == 0
    assert secret not in caplog.text


def test_invalid_cached_selection_cursor_restarts_from_zero() -> None:
    """Malformed shared state cannot suppress eligible inventory."""
    cursor_key = f"invalid-realtime-cursor-{uuid4()}"
    caches["default"].set(cursor_key, {"after_id": -1})

    assert RealtimeSubscriptionSupervisor._read_selection_cursor(cursor_key).after_id == 0
    caches["default"].delete(cursor_key)


def test_supervisor_caps_device_count_and_concurrency() -> None:
    """A supervisor never starts more inventory or live work than allowed."""
    active = 0
    maximum_active = 0
    started: list[int] = []

    async def subscribe(item: int) -> None:
        nonlocal active, maximum_active
        started.append(item)
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1

    lease = Mock()
    limits = SubscriptionLimits(max_devices=3, max_concurrency=2)
    asyncio.run(
        RealtimeSubscriptionSupervisor.run(
            items=range(10),
            subscribe=subscribe,
            lease=lease,
            limits=limits,
        )
    )

    assert started == [0, 1, 2]
    assert maximum_active == 2


def test_empty_supervisor_does_not_create_background_tasks() -> None:
    """No inventory means no subscription group or lease heartbeat."""
    subscribe = AsyncMock()

    asyncio.run(
        RealtimeSubscriptionSupervisor.run(
            items=[],
            subscribe=subscribe,
            lease=Mock(),
            limits=SubscriptionLimits(max_devices=1, max_concurrency=1),
        )
    )

    subscribe.assert_not_awaited()


def test_blocking_subscriptions_rotate_to_later_selected_devices() -> None:
    """Long-lived first connections cannot monopolize every bounded worker forever."""

    async def scenario() -> tuple[list[int], int]:
        active = 0
        maximum_active = 0
        started: list[int] = []
        later_started = asyncio.Event()
        never_complete = asyncio.Event()

        async def subscribe(item: int) -> None:
            nonlocal active, maximum_active
            started.append(item)
            active += 1
            maximum_active = max(maximum_active, active)
            if item == 2:
                later_started.set()
            try:
                await never_complete.wait()
            finally:
                active -= 1

        supervisor = asyncio.create_task(
            RealtimeSubscriptionSupervisor.run(
                items=range(3),
                subscribe=subscribe,
                lease=Mock(),
                limits=SubscriptionLimits(
                    max_devices=3,
                    max_concurrency=2,
                    rotation_seconds=0.01,
                    reconnect_delay_seconds=10,
                ),
            )
        )
        try:
            await asyncio.wait_for(later_started.wait(), timeout=1)
        finally:
            supervisor.cancel()
            results = await asyncio.gather(supervisor, return_exceptions=True)
            result = results[0]
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                raise result
        return started, maximum_active

    started, maximum_active = asyncio.run(scenario())

    assert started[:2] == [0, 1]
    assert 2 in started
    assert maximum_active == 2


@pytest.mark.django_db(transaction=True)
def test_one_supervisor_lifetime_reloads_rows_beyond_device_window() -> None:
    """A blocking first DB window cannot starve eligible rows beyond ``max_devices``."""
    manufacturer = ManufacturerFactory(code=f"lifetime-{uuid4().hex[:8]}")
    chassis = [
        WirelessChassisFactory(
            manufacturer=manufacturer,
            api_device_id=f"lifetime-device-{index}",
            status="online",
        )
        for index in range(4)
    ]
    transport = f"lifetime-{uuid4()}"
    cursor_key = RealtimeSubscriptionSupervisor._selection_cursor_key(
        transport=transport,
        scope=manufacturer.pk,
    )
    caches["default"].delete(cursor_key)

    def load_window() -> list[WirelessChassis]:
        return RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=manufacturer.wirelesschassis_set.filter(status="online"),
            transport=transport,
            scope=manufacturer.pk,
            limit=2,
        )

    initial_window = load_window()
    following_window = load_window()

    async def scenario() -> tuple[list[int], int]:
        active = 0
        maximum_active = 0
        started: list[int] = []
        later_started = asyncio.Event()
        never_complete = asyncio.Event()

        async def subscribe(item: WirelessChassis) -> None:
            nonlocal active, maximum_active
            item_pk = int(item.pk)
            started.append(item_pk)
            active += 1
            maximum_active = max(maximum_active, active)
            if item_pk == chassis[2].pk:
                later_started.set()
            try:
                await never_complete.wait()
            finally:
                active -= 1

        reload_items = AsyncMock(side_effect=[following_window, []])

        supervisor = asyncio.create_task(
            RealtimeSubscriptionSupervisor.run(
                items=initial_window,
                subscribe=subscribe,
                lease=Mock(),
                limits=SubscriptionLimits(
                    max_devices=2,
                    max_concurrency=1,
                    rotation_seconds=0.01,
                    reconnect_delay_seconds=0,
                ),
                reload_items=reload_items,
            )
        )
        try:
            await asyncio.wait_for(later_started.wait(), timeout=1)
        finally:
            supervisor.cancel()
            results = await asyncio.gather(supervisor, return_exceptions=True)
            result = results[0]
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                raise result
        return started, maximum_active

    started, maximum_active = asyncio.run(scenario())

    assert started[:3] == [chassis[0].pk, chassis[1].pk, chassis[2].pk]
    assert maximum_active == 1
    caches["default"].delete(cursor_key)


def test_subscription_round_contains_and_redacts_connection_failures(caplog) -> None:
    """One failed device cannot stop later work or leak transport exception details."""
    secret = "private-subscription-credential"
    started: list[int] = []

    async def subscribe(item: int) -> None:
        started.append(item)
        if item == 1:
            raise RuntimeError(secret)

    timed_out = asyncio.run(
        RealtimeSubscriptionSupervisor._run_subscription_round(
            items=[1, 2],
            subscribe=subscribe,
            max_concurrency=1,
            rotation_seconds=1,
        )
    )

    assert timed_out is False
    assert started == [1, 2]
    assert secret not in caplog.text


def test_timed_out_round_reconnects_after_configured_delay(monkeypatch) -> None:
    """A long-lived round pauses before beginning the next bounded cycle."""
    run_round = AsyncMock(side_effect=[True, False])
    sleep = AsyncMock()
    monkeypatch.setattr(
        RealtimeSubscriptionSupervisor,
        "_run_subscription_round",
        run_round,
    )
    monkeypatch.setattr(supervisor_module.asyncio, "sleep", sleep)

    asyncio.run(
        RealtimeSubscriptionSupervisor._run_bounded_subscriptions(
            items=[1],
            subscribe=AsyncMock(),
            max_concurrency=1,
            rotation_seconds=1,
            reconnect_delay_seconds=2,
            max_devices=1,
            reload_items=None,
        )
    )

    sleep.assert_awaited_once_with(2)


def test_reload_callback_keeps_supervisor_alive_after_clean_disconnect() -> None:
    """Completed transport coroutines advance inventory instead of stopping supervision."""
    started: list[int] = []
    reload_items = AsyncMock(side_effect=[[2], []])

    async def subscribe(item: int) -> None:
        started.append(item)

    asyncio.run(
        RealtimeSubscriptionSupervisor.run(
            items=[1],
            subscribe=subscribe,
            lease=Mock(),
            limits=SubscriptionLimits(
                max_devices=1,
                max_concurrency=1,
                reconnect_delay_seconds=0,
            ),
            reload_items=reload_items,
        )
    )

    assert started == [1, 2]
    assert reload_items.await_count == 2


def test_lost_lease_cancels_blocking_subscriptions(monkeypatch) -> None:
    """Lease ownership loss stops every live device worker."""
    monkeypatch.setattr(supervisor_module, "SUBSCRIPTION_LEASE_REFRESH_SECONDS", 0)
    lease = Mock()
    lease.refresh.return_value = False
    refresh_async = AsyncMock(side_effect=lease.refresh)
    monkeypatch.setattr(
        supervisor_module,
        "sync_to_async",
        Mock(return_value=refresh_async),
    )

    async def subscribe(_item: int) -> None:
        await asyncio.Event().wait()

    with pytest.raises(SubscriptionLeaseLostError, match="lease was lost"):
        asyncio.run(
            RealtimeSubscriptionSupervisor.run(
                items=[1],
                subscribe=subscribe,
                lease=lease,
                limits=SubscriptionLimits(max_devices=1, max_concurrency=1),
            )
        )

    refresh_async.assert_awaited_once_with()


def test_supervisor_consumes_only_the_capped_generator_prefix() -> None:
    """Bounding a lazy inventory never materializes its untrusted tail."""
    consumed: list[int] = []

    def items():
        for item in range(100):
            consumed.append(item)
            yield item

    async def subscribe(_item: int) -> None:
        await asyncio.sleep(0)

    asyncio.run(
        RealtimeSubscriptionSupervisor.run(
            items=items(),
            subscribe=subscribe,
            lease=Mock(),
            limits=SubscriptionLimits(max_devices=3, max_concurrency=2),
        )
    )

    assert consumed == [0, 1, 2]


def test_device_https_url_formats_ipv4_and_ipv6_authorities() -> None:
    """IPv6 literals are bracketed while IPv4 addresses remain plain."""
    assert build_device_https_url(ip_address="192.0.2.10", port=8443) == "https://192.0.2.10:8443"
    assert (
        build_device_https_url(ip_address="2001:db8::10", port="443")
        == "https://[2001:db8::10]:443"
    )


@pytest.mark.parametrize("port", [0, 65536, True, None, "invalid"])
def test_device_https_url_rejects_invalid_ports(port: object) -> None:
    """Invalid ports fail before constructing a manufacturer client."""
    with pytest.raises(ValueError, match="between 1 and 65535"):
        build_device_https_url(ip_address="192.0.2.10", port=port)


def test_device_https_url_rejects_non_ip_hosts_without_echoing_input() -> None:
    """The client origin cannot be redirected to a hostname or malformed authority."""
    with pytest.raises(ValueError, match="Device IP address is invalid") as error:
        build_device_https_url(ip_address="private-hostname.example", port=443)

    assert "private-hostname" not in str(error.value)
