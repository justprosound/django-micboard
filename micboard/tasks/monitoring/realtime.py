"""Native Huey task boundary for realtime subscriptions."""

from __future__ import annotations

from micboard.services.realtime.subscription_runner import run_realtime_subscriptions


def start_realtime_subscriptions(
    manufacturer_id: int,
    chassis_id: int | None = None,
) -> None:
    """Run realtime subscriptions using queue-safe persisted model identifiers."""
    run_realtime_subscriptions(manufacturer_id, chassis_id=chassis_id)
