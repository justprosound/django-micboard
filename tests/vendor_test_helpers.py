"""Shared deterministic doubles for built-in vendor integration tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from micboard.services.common.base import rate_limiter as limiter_module


def disable_rate_limit_waits(monkeypatch) -> None:
    """Keep decorated client methods deterministic without changing production code."""
    monkeypatch.setattr(limiter_module.cache, "get", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(limiter_module.cache, "set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(limiter_module.time, "sleep", lambda *_args, **_kwargs: None)


def vendor_api(*responses):
    """Return a minimal vendor API facade with ordered request responses."""
    return SimpleNamespace(_make_request=Mock(side_effect=responses))


class DirectAsyncAdapter:
    """Execute sync WebSocket adapters inline for deterministic unit tests."""

    def __call__(self, function, **_kwargs):
        async def invoke(*args, **kwargs):
            return function(*args, **kwargs)

        return invoke


class VendorEventSocket:
    """WebSocket double providing a handshake plus one device event."""

    async def recv(self):
        return '{"transportId": "transport"}'

    def __aiter__(self):
        self.messages = iter(['{"status": "online"}'])
        return self

    async def __anext__(self):
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class VendorConnection:
    """Async context manager optionally failing during connection setup."""

    def __init__(self, *, error: BaseException | None = None):
        self.error = error

    async def __aenter__(self):
        if self.error:
            raise self.error
        return VendorEventSocket()

    async def __aexit__(self, *_args):
        return None
