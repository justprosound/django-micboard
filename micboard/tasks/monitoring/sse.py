"""Native Huey task boundary for SSE subscriptions."""

from __future__ import annotations

from micboard.services.realtime.sse_subscription_service import run_sse_subscriptions


def start_sse_subscriptions(
    manufacturer_id: int,
    chassis_id: int | None = None,
) -> None:
    """Run SSE subscriptions using queue-safe persisted model identifiers."""
    run_sse_subscriptions(manufacturer_id, chassis_id=chassis_id)
