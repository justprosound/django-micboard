"""Native Huey task boundary for Shure WebSocket subscriptions."""

from __future__ import annotations

from micboard.services.realtime.shure_websocket_subscription_service import (
    run_shure_websocket_subscriptions,
)


def start_shure_websocket_subscriptions(
    manufacturer_id: int,
    chassis_id: int | None = None,
) -> None:
    """Run Shure WebSocket subscriptions using persisted model identifiers."""
    run_shure_websocket_subscriptions(manufacturer_id, chassis_id=chassis_id)
