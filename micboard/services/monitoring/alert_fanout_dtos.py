"""Typed workload budgets for alert fanout."""

from __future__ import annotations

from django.conf import settings

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

DEFAULT_ALERT_MAX_ASSIGNMENTS = 100
HARD_ALERT_MAX_ASSIGNMENTS = 500
DEFAULT_ALERT_MAX_RECIPIENTS = 250
HARD_ALERT_MAX_RECIPIENTS = 1_000
DEFAULT_ALERT_MAX_DELIVERIES = 250
HARD_ALERT_MAX_DELIVERIES = 1_000


def _bounded_setting(name: str, *, default: int, hard_limit: int) -> int:
    """Return a positive integer setting clamped to its package hard limit."""
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), hard_limit)


class AlertFanoutBudget(PydanticBaseDTO):
    """Mutable counters enforcing one alert run's hard workload ceilings."""

    assignment_limit: int = Field(ge=1, le=HARD_ALERT_MAX_ASSIGNMENTS)
    recipient_limit: int = Field(ge=1, le=HARD_ALERT_MAX_RECIPIENTS)
    delivery_limit: int = Field(ge=1, le=HARD_ALERT_MAX_DELIVERIES)
    assignments_evaluated: int = Field(default=0, ge=0, le=HARD_ALERT_MAX_ASSIGNMENTS)
    recipients_evaluated: int = Field(default=0, ge=0, le=HARD_ALERT_MAX_RECIPIENTS)
    delivery_attempts: int = Field(default=0, ge=0, le=HARD_ALERT_MAX_DELIVERIES)
    assignments_truncated: bool = False
    recipients_truncated: bool = False
    deliveries_truncated: bool = False

    @classmethod
    def from_settings(cls) -> AlertFanoutBudget:
        """Build a budget from host settings without permitting unbounded values."""
        return cls(
            assignment_limit=_bounded_setting(
                "MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS",
                default=DEFAULT_ALERT_MAX_ASSIGNMENTS,
                hard_limit=HARD_ALERT_MAX_ASSIGNMENTS,
            ),
            recipient_limit=_bounded_setting(
                "MICBOARD_POLL_ALERT_MAX_RECIPIENTS",
                default=DEFAULT_ALERT_MAX_RECIPIENTS,
                hard_limit=HARD_ALERT_MAX_RECIPIENTS,
            ),
            delivery_limit=_bounded_setting(
                "MICBOARD_POLL_ALERT_MAX_DELIVERIES",
                default=DEFAULT_ALERT_MAX_DELIVERIES,
                hard_limit=HARD_ALERT_MAX_DELIVERIES,
            ),
        )

    @property
    def remaining_assignments(self) -> int:
        """Return how many assignment rows may still be evaluated."""
        return self.assignment_limit - self.assignments_evaluated

    @property
    def remaining_recipients(self) -> int:
        """Return how many recipient rows may still be evaluated."""
        return self.recipient_limit - self.recipients_evaluated

    @property
    def remaining_deliveries(self) -> int:
        """Return how many alert delivery attempts remain."""
        return self.delivery_limit - self.delivery_attempts

    @property
    def truncated(self) -> bool:
        """Return whether any fanout dimension reached a bounded partial page."""
        return self.assignments_truncated or self.recipients_truncated or self.deliveries_truncated

    @property
    def exhausted(self) -> bool:
        """Return whether another unit could not receive the complete fanout pipeline."""
        return (
            self.remaining_assignments == 0
            or self.remaining_recipients == 0
            or self.remaining_deliveries == 0
        )

    def record_assignments(self, count: int, *, truncated: bool) -> None:
        """Record a bounded assignment page."""
        if count < 0 or count > self.remaining_assignments:
            raise ValueError("Assignment count exceeds the remaining alert budget")
        self.assignments_evaluated += count
        self.assignments_truncated = self.assignments_truncated or truncated

    def record_recipients(self, count: int, *, truncated: bool) -> None:
        """Record a bounded recipient page."""
        if count < 0 or count > self.remaining_recipients:
            raise ValueError("Recipient count exceeds the remaining alert budget")
        self.recipients_evaluated += count
        self.recipients_truncated = self.recipients_truncated or truncated

    def claim_delivery(self) -> bool:
        """Reserve one alert persistence/delivery attempt if capacity remains."""
        if self.remaining_deliveries <= 0:
            self.deliveries_truncated = True
            return False
        self.delivery_attempts += 1
        return True
