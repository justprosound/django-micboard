"""Security, fairness, and hard-budget contracts for alert fanout."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import override_settings

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from micboard.services.monitoring.alert_fanout_dtos import (
    HARD_ALERT_MAX_ASSIGNMENTS,
    HARD_ALERT_MAX_DELIVERIES,
    HARD_ALERT_MAX_RECIPIENTS,
    AlertFanoutBudget,
)
from micboard.services.monitoring.alert_fanout_service import AlertFanoutService
from micboard.services.monitoring.alerts import AlertManager
from tests.factories.base import UserFactory
from tests.factories.monitoring import PerformerAssignmentFactory


def _budget(
    *,
    assignments: int = 10,
    recipients: int = 10,
    deliveries: int = 10,
) -> AlertFanoutBudget:
    return AlertFanoutBudget(
        assignment_limit=assignments,
        recipient_limit=recipients,
        delivery_limit=deliveries,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("revoked", ["user", "group"])
def test_single_site_fanout_rejects_inactive_recipient_or_group(
    assigned_unit,
    revoked: str,
) -> None:
    """Single-site mode does not bypass current user and assignment authorization."""
    if revoked == "user":
        assigned_unit.user.is_active = False
        assigned_unit.user.save(update_fields=["is_active"])
    else:
        assigned_unit.assignment.monitoring_group.is_active = False
        assigned_unit.assignment.monitoring_group.save(update_fields=["is_active"])

    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email"
    ) as send_email:
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )

    assert alert is None
    assert not Alert.objects.exists()
    send_email.assert_not_called()


@pytest.mark.django_db
def test_unauthenticated_recipient_is_rejected_before_single_site_shortcut(assigned_unit) -> None:
    """An anonymous object cannot become an alert recipient in single-site mode."""
    assert (
        AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=AnonymousUser(),
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
        is None
    )
    assert not Alert.objects.exists()


@pytest.mark.django_db
def test_assignment_page_excludes_inactive_monitoring_groups(assigned_unit) -> None:
    """Every active-assignment query also requires an active owning group."""
    assigned_unit.assignment.monitoring_group.is_active = False
    assigned_unit.assignment.monitoring_group.save(update_fields=["is_active"])
    budget = _budget()

    assert (
        AlertFanoutService.assignments_for_unit(
            unit=assigned_unit.unit,
            scope="inactive-group",
            budget=budget,
        )
        == []
    )
    assert budget.assignments_evaluated == 0


@pytest.mark.django_db
def test_revocation_before_persistence_and_before_email_is_rechecked(assigned_unit) -> None:
    """Authorization changes at either delivery boundary fail closed."""
    with (
        patch.object(AlertFanoutService, "current_authorized_recipient", return_value=None),
        patch("micboard.services.monitoring.alert_delivery_service.send_alert_email") as send_email,
    ):
        denied = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
    assert denied is None
    assert not Alert.objects.exists()
    send_email.assert_not_called()

    with (
        patch.object(
            AlertFanoutService,
            "current_authorized_recipient",
            side_effect=[assigned_unit.user, None],
        ),
        patch("micboard.services.monitoring.alert_delivery_service.send_alert_email") as send_email,
    ):
        persisted = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
    assert persisted is not None
    assert Alert.objects.filter(pk=persisted.pk).exists()
    send_email.assert_not_called()


@pytest.mark.django_db
def test_assignment_pages_use_cap_plus_one_and_rotate_without_starvation(assigned_unit) -> None:
    """A hard assignment page advances deterministically through later rows."""
    assignments = [assigned_unit.assignment]
    assignments.extend(
        PerformerAssignmentFactory(wireless_unit=assigned_unit.unit) for _ in range(3)
    )
    assignments.sort(key=lambda assignment: assignment.pk)
    key = AlertFanoutService._assignment_cursor_key(
        unit_id=assigned_unit.unit.pk,
        scope="test-assignments",
    )
    cache.delete(key)

    first_budget = _budget(assignments=2)
    first = AlertFanoutService.assignments_for_unit(
        unit=assigned_unit.unit,
        scope="test-assignments",
        budget=first_budget,
    )
    second_budget = _budget(assignments=2)
    second = AlertFanoutService.assignments_for_unit(
        unit=assigned_unit.unit,
        scope="test-assignments",
        budget=second_budget,
    )
    third_budget = _budget(assignments=2)
    third = AlertFanoutService.assignments_for_unit(
        unit=assigned_unit.unit,
        scope="test-assignments",
        budget=third_budget,
    )

    assert [item.pk for item in first] == [item.pk for item in assignments[:2]]
    assert [item.pk for item in second] == [item.pk for item in assignments[2:]]
    assert [item.pk for item in third] == [item.pk for item in assignments[:2]]
    assert first_budget.assignments_truncated
    assert second_budget.assignments_truncated
    assert third_budget.assignments_truncated


@pytest.mark.django_db
def test_recipient_pages_use_cap_plus_one_and_rotate_without_starvation(assigned_unit) -> None:
    """A hard recipient page eventually visits every group member and wraps."""
    recipients = [assigned_unit.user, UserFactory(), UserFactory(), UserFactory(), UserFactory()]
    assigned_unit.assignment.monitoring_group.users.add(*recipients[1:])
    recipients.sort(key=lambda user: user.pk)
    key = AlertFanoutService._recipient_cursor_key(
        unit_id=assigned_unit.unit.pk,
        scope="test-recipients",
    )
    cache.delete(key)

    pages: list[list[int]] = []
    budgets: list[AlertFanoutBudget] = []
    for _ in range(3):
        budget = _budget(recipients=2)
        mapping = AlertFanoutService.recipients_for_assignments(
            unit=assigned_unit.unit,
            assignments=[assigned_unit.assignment],
            scope="test-recipients",
            budget=budget,
        )
        pages.append([user.pk for user in mapping[assigned_unit.assignment.pk]])
        budgets.append(budget)

    assert pages == [
        [user.pk for user in recipients[:2]],
        [user.pk for user in recipients[2:4]],
        [recipients[4].pk, recipients[0].pk],
    ]
    assert all(budget.recipients_truncated for budget in budgets)


@pytest.mark.django_db
def test_cache_outage_does_not_suppress_bounded_fanout(assigned_unit, caplog) -> None:
    """Cursor storage is optional and exception details remain redacted."""
    assigned_unit.assignment.monitoring_group.users.add(UserFactory())
    secret = "redis://operator:private@example.test"
    budget = _budget(assignments=1, recipients=1)
    with (
        patch(
            "micboard.services.monitoring.alert_fanout_service.cache.get",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.monitoring.alert_fanout_service.cache.set",
            side_effect=RuntimeError(secret),
        ),
    ):
        assignments = AlertFanoutService.assignments_for_unit(
            unit=assigned_unit.unit,
            scope="cache-outage",
            budget=budget,
        )
        recipients = AlertFanoutService.recipients_for_assignments(
            unit=assigned_unit.unit,
            assignments=assignments,
            scope="cache-outage",
            budget=budget,
        )

    assert assignments == [assigned_unit.assignment]
    assert len(recipients[assigned_unit.assignment.pk]) == 1
    assert secret not in caplog.text


@pytest.mark.django_db
def test_exact_delivery_budget_caps_persistence_and_email(assigned_unit) -> None:
    """No candidate beyond the delivery ceiling reaches persistence or email."""
    recipients = [assigned_unit.user, UserFactory(), UserFactory(), UserFactory(), UserFactory()]
    assigned_unit.assignment.monitoring_group.users.add(*recipients[1:])
    assigned_unit.unit.battery = 0
    budget = _budget(assignments=5, recipients=10, deliveries=2)

    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email",
        return_value=True,
    ) as send_email:
        AlertManager().check_wireless_unit_alerts(assigned_unit.unit, budget=budget)

    assert Alert.objects.count() == 2
    assert send_email.call_count == 2
    assert budget.delivery_attempts == 2
    assert budget.deliveries_truncated


@override_settings(
    MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS=100_000,
    MICBOARD_POLL_ALERT_MAX_RECIPIENTS=100_000,
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=100_000,
)
def test_budget_settings_cannot_exceed_package_hard_caps() -> None:
    """Host configuration cannot turn any fanout dimension into an unbounded run."""
    budget = AlertFanoutBudget.from_settings()
    assert budget.assignment_limit == HARD_ALERT_MAX_ASSIGNMENTS
    assert budget.recipient_limit == HARD_ALERT_MAX_RECIPIENTS
    assert budget.delivery_limit == HARD_ALERT_MAX_DELIVERIES


def test_budget_rejects_invalid_accounting_and_marks_exhaustion() -> None:
    """Budget counters cannot be overdrawn or silently ignore exhaustion."""
    budget = _budget(assignments=1, recipients=1, deliveries=1)
    with pytest.raises(ValueError, match="Assignment count"):
        budget.record_assignments(2, truncated=False)
    with pytest.raises(ValueError, match="Recipient count"):
        budget.record_recipients(-1, truncated=False)

    assert budget.claim_delivery()
    assert not budget.claim_delivery()
    assert budget.delivery_attempts == 1
    assert budget.truncated


@override_settings(
    MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS=True,
    MICBOARD_POLL_ALERT_MAX_RECIPIENTS=object(),
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=0,
)
def test_budget_settings_reject_boolean_invalid_and_nonpositive_values() -> None:
    """Malformed host settings fall back or clamp to safe positive defaults."""
    budget = AlertFanoutBudget.from_settings()
    assert budget.assignment_limit == 100
    assert budget.recipient_limit == 250
    assert budget.delivery_limit == 1


@pytest.mark.django_db
def test_exhausted_and_empty_fanout_pages_do_no_additional_work(assigned_unit) -> None:
    """Exhausted dimensions and empty recipient sets return bounded empty pages."""
    assignment_budget = _budget(assignments=1)
    assignment_budget.record_assignments(1, truncated=False)
    assert (
        AlertFanoutService.assignments_for_unit(
            unit=assigned_unit.unit,
            scope="exhausted-assignment",
            budget=assignment_budget,
        )
        == []
    )
    assert assignment_budget.assignments_truncated

    recipient_budget = _budget(recipients=1)
    recipient_budget.record_recipients(1, truncated=False)
    assert (
        AlertFanoutService.recipients_for_assignments(
            unit=assigned_unit.unit,
            assignments=[assigned_unit.assignment],
            scope="exhausted-recipient",
            budget=recipient_budget,
        )
        == {}
    )
    assert recipient_budget.recipients_truncated

    assert (
        AlertFanoutService.recipients_for_assignments(
            unit=assigned_unit.unit,
            assignments=[],
            scope="empty-assignments",
            budget=_budget(),
        )
        == {}
    )
    assigned_unit.assignment.monitoring_group.users.clear()
    assert (
        AlertFanoutService.recipients_for_assignments(
            unit=assigned_unit.unit,
            assignments=[assigned_unit.assignment],
            scope="empty-recipients",
            budget=_budget(),
        )
        == {}
    )


@pytest.mark.django_db
def test_fresh_authorization_rejects_unsaved_or_inactive_objects(assigned_unit) -> None:
    """Authorization fails closed before querying with missing IDs or stale active flags."""
    assigned_unit.unit.pk = None
    assert (
        AlertFanoutService.current_authorized_recipient(
            unit=assigned_unit.unit,
            assignment=assigned_unit.assignment,
            user=assigned_unit.user,
        )
        is None
    )
    assigned_unit.unit.pk = assigned_unit.assignment.wireless_unit_id
    assigned_unit.user.is_active = False
    assigned_unit.user.save(update_fields=["is_active"])
    assert (
        AlertFanoutService.current_authorized_recipient(
            unit=assigned_unit.unit,
            assignment=assigned_unit.assignment,
            user=assigned_unit.user,
        )
        is None
    )


def test_invalid_fanout_cursor_values_reset_to_start() -> None:
    """Malformed cache values cannot influence bounded page ordering."""
    with patch("micboard.services.monitoring.alert_fanout_service.cache.get", return_value=True):
        assert AlertFanoutService._read_cursor("invalid") == 0
    with patch(
        "micboard.services.monitoring.alert_fanout_service.cache.get",
        return_value=(True, 0),
    ):
        assert AlertFanoutService._read_pair_cursor("invalid") == (0, 0)
