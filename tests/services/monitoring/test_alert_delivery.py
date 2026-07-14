"""Alert deduplication and recipient-delivery contracts."""

from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.services.monitoring.alerts import AlertManager
from tests.factories.base import UserFactory
from tests.factories.monitoring import UserAlertPreferenceFactory


@pytest.mark.django_db
def test_create_alert_requires_channel_locks_and_marks_delivery_failures(
    assigned_unit,
    caplog,
) -> None:
    """Creation fails safely, serializes dedupe, and exposes delivery failures."""
    assigned_unit.unit.assigned_resource = None
    assert (
        AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="No channel",
        )
        is None
    )

    assigned_unit.unit.assigned_resource = assigned_unit.channel
    budget = AlertFanoutBudget(
        assignment_limit=1,
        recipient_limit=1,
        delivery_limit=1,
    )
    with patch.object(AlertFanoutBudget, "claim_delivery", return_value=False):
        assert (
            AlertDeliveryService.create_alert(
                unit=assigned_unit.unit,
                user=assigned_unit.user,
                performer_assignment=assigned_unit.assignment,
                alert_type="signal_loss",
                message="Budget exhausted",
                budget=budget,
            )
            is None
        )

    with (
        patch.object(
            RFChannel.objects,
            "select_for_update",
            wraps=RFChannel.objects.select_for_update,
        ) as select_for_update,
        patch(
            "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification",
            side_effect=RuntimeError("smtp://operator:secret@example.test"),
        ),
    ):
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )

    assert alert is not None
    select_for_update.assert_called_once_with()
    assert "operator:secret" not in caplog.text
    assert "error details redacted" in caplog.text
    alert.refresh_from_db()
    assert alert.status == "failed"

    Alert.objects.all().delete()
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification",
        return_value=False,
    ):
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="audio_low",
            message="Audio low",
        )
    assert alert is not None
    alert.refresh_from_db()
    assert alert.status == "failed"


@pytest.mark.django_db
def test_alert_email_honors_delivery_method_quiet_hours_and_override(assigned_unit) -> None:
    """Recipient preferences gate email without suppressing the in-app alert."""
    preferences = UserAlertPreferenceFactory(
        user=assigned_unit.user,
        notification_method="websocket",
        email_address="override@example.test",
    )
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ) as send_email:
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
    assert alert is not None
    send_email.assert_not_called()

    Alert.objects.all().delete()
    preferences.notification_method = "email"
    preferences.quiet_hours_enabled = True
    preferences.quiet_hours_start = time.min
    preferences.quiet_hours_end = time.max
    preferences.save()
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ) as send_email:
        AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
    send_email.assert_not_called()

    Alert.objects.all().delete()
    preferences.quiet_hours_enabled = False
    preferences.save(update_fields=["quiet_hours_enabled"])
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification",
        return_value=True,
    ) as send_email:
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
    send_email.assert_called_once_with(alert, recipients=["override@example.test"])

    Alert.objects.all().delete()
    preferences.email_address = ""
    preferences.save(update_fields=["email_address"])
    assigned_unit.user.email = ""
    assigned_unit.user.save(update_fields=["email"])
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ) as send_email:
        alert = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="audio_low",
            message="No recipient address",
        )
    assert alert is not None
    send_email.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("interval", "age_minutes", "expected_count"),
    [(None, 4, 1), (None, 6, 2), (0, 0, 2), (30, 29, 1), (30, 31, 2)],
)
def test_alert_deduplication_honors_recipient_interval(
    assigned_unit,
    interval: int | None,
    age_minutes: int,
    expected_count: int,
) -> None:
    """Default, disabled, and custom repeat windows use the persisted preference."""
    if interval is not None:
        UserAlertPreferenceFactory(user=assigned_unit.user, min_alert_interval=interval)
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification",
        return_value=True,
    ):
        first = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost",
        )
        assert first is not None
        Alert.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        second = AlertDeliveryService.create_alert(
            unit=assigned_unit.unit,
            user=assigned_unit.user,
            performer_assignment=assigned_unit.assignment,
            alert_type="signal_loss",
            message="Signal lost again",
        )

    assert Alert.objects.count() == expected_count
    assert second is not None
    assert (second.pk == first.pk) is (expected_count == 1)


@pytest.mark.django_db
def test_offline_alert_recipient_loading_is_query_bounded(
    assigned_unit,
    django_assert_num_queries,
) -> None:
    """Offline fanout prefetches preferences instead of querying once per recipient."""
    recipients = [assigned_unit.user, UserFactory(), UserFactory()]
    assigned_unit.assignment.monitoring_group.users.add(*recipients[1:])
    for user in recipients:
        UserAlertPreferenceFactory(user=user)
    assigned_unit.unit.status = "offline"
    manager = AlertManager()

    with (
        django_assert_num_queries(3),
        patch.object(AlertDeliveryService, "create_alert") as create_alert,
    ):
        manager.check_hardware_offline_alerts(assigned_unit.unit)

    assert create_alert.call_count == 3
