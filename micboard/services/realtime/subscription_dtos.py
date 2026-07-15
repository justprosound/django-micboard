"""Typed limits and cursor state for realtime subscription supervisors."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

DEFAULT_MAX_SUBSCRIPTION_DEVICES = 64
DEFAULT_MAX_SUBSCRIPTION_CONCURRENCY = 16
HARD_MAX_SUBSCRIPTION_DEVICES = 256
HARD_MAX_SUBSCRIPTION_CONCURRENCY = 64
DEFAULT_SUBSCRIPTION_ROTATION_SECONDS = 300.0
HARD_MAX_SUBSCRIPTION_ROTATION_SECONDS = 3_600.0
DEFAULT_SUBSCRIPTION_RECONNECT_DELAY_SECONDS = 1.0
HARD_MAX_SUBSCRIPTION_RECONNECT_DELAY_SECONDS = 60.0


class SubscriptionLimits(PydanticBaseDTO):
    """Validated limits for one realtime subscription supervisor."""

    max_devices: int = Field(ge=1, le=HARD_MAX_SUBSCRIPTION_DEVICES)
    max_concurrency: int = Field(ge=1, le=HARD_MAX_SUBSCRIPTION_CONCURRENCY)
    rotation_seconds: float = Field(
        default=DEFAULT_SUBSCRIPTION_ROTATION_SECONDS,
        gt=0,
        le=HARD_MAX_SUBSCRIPTION_ROTATION_SECONDS,
    )
    reconnect_delay_seconds: float = Field(
        default=DEFAULT_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
        ge=0,
        le=HARD_MAX_SUBSCRIPTION_RECONNECT_DELAY_SECONDS,
    )


class SubscriptionSelectionCursor(PydanticBaseDTO):
    """Cache-safe circular inventory cursor for one transport scope."""

    after_id: int = Field(default=0, ge=0)
