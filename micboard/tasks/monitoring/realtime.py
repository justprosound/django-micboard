"""Native Huey task boundary for realtime subscriptions."""

import logging

from micboard.services.realtime.subscription_runner import run_realtime_subscriptions

logger = logging.getLogger(__name__)


def start_realtime_subscriptions(
    manufacturer_id: int,
    chassis_id: int | None = None,
) -> str:
    """Run realtime subscriptions using queue-safe persisted model identifiers.

    Returns the run's outcome as a string so the queue records how it ended.
    """
    outcome = run_realtime_subscriptions(manufacturer_id, chassis_id=chassis_id)
    logger.info(
        "Realtime run for manufacturer ID %s ended: %s",
        manufacturer_id,
        outcome.value,
        extra={"event.action": "realtime-run", "micboard.realtime.outcome": outcome.value},
    )
    return outcome.value
