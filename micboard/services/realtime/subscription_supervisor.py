"""Bounded, lease-backed orchestration for realtime device subscriptions."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import secrets
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from itertools import islice
from typing import Any, TypeVar

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.db import models
from django.db.models import QuerySet

from asgiref.sync import sync_to_async
from pydantic import ValidationError

from micboard.exceptions import SubscriptionLeaseLostError
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
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

SUBSCRIPTION_LEASE_SECONDS = 60
SUBSCRIPTION_LEASE_REFRESH_SECONDS = 15
SUBSCRIPTION_SELECTION_CURSOR_SECONDS = 30 * 24 * 60 * 60

SubscriptionItem = TypeVar("SubscriptionItem")
SubscriptionModel = TypeVar("SubscriptionModel", bound=models.Model)


def build_device_https_url(*, ip_address: object, port: object = 443) -> str:
    """Build an HTTPS origin with correct IPv4/IPv6 authority syntax."""
    try:
        parsed_address = ipaddress.ip_address(str(ip_address))
    except ValueError:
        raise ValueError("Device IP address is invalid") from None

    if isinstance(port, bool) or not isinstance(port, int | str):
        raise ValueError("Device port must be between 1 and 65535")
    try:
        parsed_port = int(port)
    except ValueError:
        raise ValueError("Device port must be between 1 and 65535") from None
    if not 1 <= parsed_port <= 65535:
        raise ValueError("Device port must be between 1 and 65535")

    host = (
        f"[{parsed_address.compressed}]"
        if isinstance(parsed_address, ipaddress.IPv6Address)
        else parsed_address.compressed
    )
    return f"https://{host}:{parsed_port}"


@dataclass(frozen=True, slots=True)
class RealtimeSubscriptionLease:
    """Ownership token for one cache-backed supervisor lease."""

    cache: BaseCache
    cache_key: str
    token: str

    def refresh(self) -> bool:
        """Renew the lease only while this worker still owns it."""
        try:
            if self.cache.get(self.cache_key) != self.token:
                return False
            if not self.cache.touch(self.cache_key, SUBSCRIPTION_LEASE_SECONDS):
                return False
            return self.cache.get(self.cache_key) == self.token  # type: ignore[no-any-return]
        except Exception as exc:
            logger.exception(
                "Failed to renew realtime subscription supervisor lease",
                exc_info=sanitized_exception_info(exc),
            )
            return False


class RealtimeSubscriptionSupervisor:
    """Run one bounded realtime subscription group under a renewable lease.

    Leases expire rather than being explicitly deleted. Generic Django caches do
    not provide atomic compare-and-delete, so deletion could remove a replacement
    owner's token. A cleanly stopped supervisor can therefore take up to one lease
    timeout before it can restart.
    """

    @classmethod
    def acquire(
        cls,
        *,
        transport: str,
        scope: str | int,
    ) -> RealtimeSubscriptionLease | None:
        """Acquire the singleton lease for a transport and manufacturer scope."""
        cache_alias = micboard_settings.get("MICBOARD_REALTIME_CACHE_ALIAS", "default")
        cache_key = f"micboard:realtime-supervisor:v1:{transport}:{scope}"
        token = secrets.token_urlsafe(24)

        try:
            subscription_cache = caches[cache_alias]
            acquired = subscription_cache.add(
                cache_key,
                token,
                timeout=SUBSCRIPTION_LEASE_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Failed to acquire realtime subscription supervisor lease",
                exc_info=sanitized_exception_info(exc),
            )
            return None

        if not acquired:
            return None
        return RealtimeSubscriptionLease(subscription_cache, cache_key, token)

    @staticmethod
    def limits() -> SubscriptionLimits:
        """Resolve host limits while enforcing package-level hard ceilings."""
        max_devices = _bounded_positive_setting(
            "MICBOARD_REALTIME_MAX_DEVICES",
            default=DEFAULT_MAX_SUBSCRIPTION_DEVICES,
            hard_limit=HARD_MAX_SUBSCRIPTION_DEVICES,
        )
        max_concurrency = _bounded_positive_setting(
            "MICBOARD_REALTIME_MAX_CONCURRENCY",
            default=DEFAULT_MAX_SUBSCRIPTION_CONCURRENCY,
            hard_limit=HARD_MAX_SUBSCRIPTION_CONCURRENCY,
        )
        rotation_seconds = _bounded_positive_float_setting(
            "MICBOARD_REALTIME_ROTATION_SECONDS",
            default=DEFAULT_SUBSCRIPTION_ROTATION_SECONDS,
            hard_limit=HARD_MAX_SUBSCRIPTION_ROTATION_SECONDS,
        )
        reconnect_delay_seconds = _bounded_positive_float_setting(
            "MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS",
            default=DEFAULT_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
            hard_limit=HARD_MAX_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
            minimum=0.0,
        )
        return SubscriptionLimits(
            max_devices=max_devices,
            max_concurrency=min(max_concurrency, max_devices),
            rotation_seconds=rotation_seconds,
            reconnect_delay_seconds=reconnect_delay_seconds,
        )

    @classmethod
    def select_fair_queryset_batch(
        cls,
        *,
        queryset: QuerySet[SubscriptionModel],
        transport: str,
        scope: str | int,
        limit: int,
    ) -> list[SubscriptionModel]:
        """Select one bounded circular inventory window without materializing its tail."""
        bounded_limit = min(max(limit, 1), HARD_MAX_SUBSCRIPTION_DEVICES)
        cursor_key = cls._selection_cursor_key(transport=transport, scope=scope)
        cursor = cls._read_selection_cursor(cursor_key)
        selected = list(queryset.filter(pk__gt=cursor.after_id).order_by("pk")[:bounded_limit])
        remaining = bounded_limit - len(selected)
        if remaining and cursor.after_id:
            selected.extend(queryset.filter(pk__lte=cursor.after_id).order_by("pk")[:remaining])
        if selected:
            cls._write_selection_cursor(
                cursor_key,
                SubscriptionSelectionCursor(after_id=int(selected[-1].pk)),
            )
        return selected

    @classmethod
    async def run(
        cls,
        *,
        items: Iterable[SubscriptionItem],
        subscribe: Callable[[SubscriptionItem], Awaitable[None]],
        lease: RealtimeSubscriptionLease,
        limits: SubscriptionLimits,
        reload_items: Callable[[], Awaitable[Iterable[SubscriptionItem]]] | None = None,
    ) -> None:
        """Run capped rotating subscriptions and cancel them if lease ownership is lost."""
        bounded_items = list(islice(items, limits.max_devices))
        if not bounded_items:
            return

        subscription_group = asyncio.create_task(
            cls._run_bounded_subscriptions(
                items=bounded_items,
                subscribe=subscribe,
                max_concurrency=limits.max_concurrency,
                rotation_seconds=limits.rotation_seconds,
                reconnect_delay_seconds=limits.reconnect_delay_seconds,
                max_devices=limits.max_devices,
                reload_items=reload_items,
            )
        )
        lease_heartbeat = asyncio.create_task(cls._maintain_lease(lease))

        try:
            completed, _pending = await asyncio.wait(
                {subscription_group, lease_heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for completed_task in completed:
                error = completed_task.exception()
                if error is not None:
                    raise error
        finally:
            subscription_group.cancel()
            lease_heartbeat.cancel()
            await asyncio.gather(
                subscription_group,
                lease_heartbeat,
                return_exceptions=True,
            )

    @staticmethod
    async def _run_bounded_subscriptions(
        *,
        items: list[SubscriptionItem],
        subscribe: Callable[[SubscriptionItem], Awaitable[None]],
        max_concurrency: int,
        rotation_seconds: float,
        reconnect_delay_seconds: float,
        max_devices: int,
        reload_items: Callable[[], Awaitable[Iterable[SubscriptionItem]]] | None,
    ) -> None:
        while True:
            timed_out = await RealtimeSubscriptionSupervisor._run_subscription_round(
                items=items,
                subscribe=subscribe,
                max_concurrency=max_concurrency,
                rotation_seconds=rotation_seconds,
            )
            if not timed_out and reload_items is None:
                return
            if reconnect_delay_seconds:
                await asyncio.sleep(reconnect_delay_seconds)
            if reload_items is not None:
                items = list(islice(await reload_items(), max_devices))
                if not items:
                    return

    @staticmethod
    async def _run_subscription_round(
        *,
        items: list[SubscriptionItem],
        subscribe: Callable[[SubscriptionItem], Awaitable[None]],
        max_concurrency: int,
        rotation_seconds: float,
    ) -> bool:
        """Process every selected item once with only a bounded worker set."""
        queue: asyncio.Queue[SubscriptionItem] = asyncio.Queue(maxsize=len(items))
        for item in items:
            queue.put_nowait(item)
        timed_out = False

        async def worker() -> None:
            nonlocal timed_out
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    async with asyncio.timeout(rotation_seconds):
                        await subscribe(item)
                except TimeoutError:
                    timed_out = True
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception(
                        "Realtime device subscription failed",
                        exc_info=sanitized_exception_info(exc),
                    )
                finally:
                    queue.task_done()

        worker_count = min(max_concurrency, len(items))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        try:
            await asyncio.gather(*workers)
        finally:
            for worker_task in workers:
                worker_task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        return timed_out

    @staticmethod
    async def _maintain_lease(lease: RealtimeSubscriptionLease) -> None:
        while True:
            await asyncio.sleep(SUBSCRIPTION_LEASE_REFRESH_SECONDS)
            refreshed = await sync_to_async(lease.refresh, thread_sensitive=True)()
            if not refreshed:
                raise SubscriptionLeaseLostError()

    @staticmethod
    def _selection_cursor_key(*, transport: str, scope: str | int) -> str:
        return f"micboard:realtime-selection-cursor:v1:{transport}:{scope}"

    @staticmethod
    def _read_selection_cursor(cursor_key: str) -> SubscriptionSelectionCursor:
        cache_alias = micboard_settings.get("MICBOARD_REALTIME_CACHE_ALIAS", "default")
        try:
            cached_value = caches[cache_alias].get(cursor_key)
            if cached_value is None:
                return SubscriptionSelectionCursor()
            return SubscriptionSelectionCursor.model_validate(cached_value)
        except (ValidationError, TypeError, ValueError):
            return SubscriptionSelectionCursor()
        except Exception as exc:
            logger.exception(
                "Could not read realtime subscription selection cursor",
                exc_info=sanitized_exception_info(exc),
            )
            return SubscriptionSelectionCursor()

    @staticmethod
    def _write_selection_cursor(
        cursor_key: str,
        cursor: SubscriptionSelectionCursor,
    ) -> None:
        cache_alias = micboard_settings.get("MICBOARD_REALTIME_CACHE_ALIAS", "default")
        try:
            caches[cache_alias].set(
                cursor_key,
                cursor.model_dump(),
                timeout=SUBSCRIPTION_SELECTION_CURSOR_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Could not persist realtime subscription selection cursor",
                exc_info=sanitized_exception_info(exc),
            )


def _bounded_positive_setting(name: str, *, default: int, hard_limit: int) -> int:
    raw_value = micboard_settings.get(name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed_value, 1), hard_limit)


def _bounded_positive_float_setting(
    name: str,
    *,
    default: float,
    hard_limit: float,
    minimum: float = 1.0,
) -> float:
    raw_value: Any = micboard_settings.get(name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed_value = float(raw_value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed_value):
        return default
    return min(max(parsed_value, minimum), hard_limit)
