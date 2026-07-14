"""Event-loop helpers for real async database regression tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable


def run_async_with_heartbeat[ResultT](awaitable: Awaitable[ResultT]) -> ResultT:
    """Run an async DB path while keeping SQLite's shared-cache loop responsive."""

    async def run() -> ResultT:
        task = asyncio.ensure_future(awaitable)
        while not task.done():
            await asyncio.sleep(0)
        return await task

    return asyncio.run(run())
