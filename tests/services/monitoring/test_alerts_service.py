"""Service-level coverage for alert creation and lifecycle behavior."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.utils import timezone

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from micboard.services.monitoring.alerts import (
    AlertManager,
    acknowledge_alert,
    get_alerts_for_user,
    resolve_alert,
)
from tests.factories.base import UserFactory
from tests.factories.monitoring import (
    AlertFactory,
    PerformerAssignmentFactory,
    UserAlertPreferenceFactory,
)


@pytest.mark.django_db
def test_alert_visibility_is_user_scoped() -> None:
    """Anonymous, regular, and superusers receive the intended queryset scope."""
    regular_user = UserFactory()
    other_user = UserFactory()
    superuser = UserFactory(is_staff=True, is_superuser=True)
    own_alert = AlertFactory(user=regular_user)
    other_alert = AlertFactory(user=other_user)

    assert not get_alerts_for_user(AnonymousUser()).exists()
    assert list(get_alerts_for_user(regular_user)) == [own_alert]
    assert set(get_alerts_for_user(superuser)) == {own_alert, other_alert}


@pytest.mark.django_db
def test_wireless_unit_checks_create_and_deduplicate_condition_alerts(assigned_unit) -> None:
    """One check emits battery, signal, and audio alerts without hourly duplicates."""
    assigned_unit.unit.battery = 10
    assigned_unit.unit.rf_level = -90
    assigned_unit.unit.audio_level = -50
    manager = AlertManager()

    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ) as send_email:
        manager.check_wireless_unit_alerts(assigned_unit.unit)
        manager.check_wireless_unit_alerts(assigned_unit.unit)

    alerts = Alert.objects.filter(user=assigned_unit.user)
    assert set(alerts.values_list("alert_type", flat=True)) == {
        "audio_low",
        "battery_critical",
        "signal_loss",
    }
    assert send_email.call_count == 3
    assert all(alert.channel_data["channel_number"] == 1 for alert in alerts)


@pytest.mark.django_db
def test_battery_preferences_select_low_alert_and_unknown_battery_is_ignored(
    assigned_unit,
) -> None:
    """Per-user thresholds distinguish low battery from unknown readings."""
    UserAlertPreferenceFactory(
        user=assigned_unit.user,
        battery_critical_threshold=5,
        battery_low_threshold=20,
    )
    assigned_unit.unit.battery = 38
    manager = AlertManager()

    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ):
        manager.check_wireless_unit_alerts(assigned_unit.unit)
    assert Alert.objects.get().alert_type == "battery_low"

    Alert.objects.all().delete()
    assigned_unit.unit.battery = 255
    manager.check_wireless_unit_alerts(assigned_unit.unit)
    assert not Alert.objects.exists()


@pytest.mark.django_db
def test_inactive_assignments_and_disabled_conditions_emit_no_alerts(assigned_unit) -> None:
    """Inactive assignments and false condition toggles stop notification fanout."""
    assigned_unit.assignment.is_active = False
    assigned_unit.assignment.save(update_fields=["is_active"])
    assigned_unit.unit.battery = 0

    AlertManager().check_wireless_unit_alerts(assigned_unit.unit)

    assert not Alert.objects.exists()

    assigned_unit.assignment.is_active = True
    assigned_unit.assignment.alert_on_battery_low = False
    assigned_unit.assignment.alert_on_signal_loss = False
    assigned_unit.assignment.alert_on_audio_low = False
    assigned_unit.assignment.save(
        update_fields=[
            "is_active",
            "alert_on_battery_low",
            "alert_on_signal_loss",
            "alert_on_audio_low",
        ]
    )
    assigned_unit.unit.rf_level = -90
    assigned_unit.unit.audio_level = -50

    AlertManager().check_wireless_unit_alerts(assigned_unit.unit)

    assert not Alert.objects.exists()


@pytest.mark.django_db
def test_alert_checks_prefetch_assignments_users_and_preferences(
    assigned_unit,
    django_assert_num_queries,
) -> None:
    """Alert retrieval remains fixed as assignments and recipients grow."""
    second_assignment = PerformerAssignmentFactory(
        wireless_unit=assigned_unit.unit,
        alert_on_audio_low=True,
    )
    second_assignment.monitoring_group.users.add(UserFactory(), UserFactory())
    UserAlertPreferenceFactory(user=assigned_unit.user)
    assigned_unit.unit.battery = 10
    assigned_unit.unit.rf_level = -90
    assigned_unit.unit.audio_level = -50
    manager = AlertManager()

    with (
        django_assert_num_queries(3),
        patch.object(AlertDeliveryService, "create_alert") as create_alert,
    ):
        manager.check_wireless_unit_alerts(assigned_unit.unit)

    assert create_alert.call_count == 9


@pytest.mark.django_db
def test_offline_checks_notify_group_users_only_when_device_is_offline(assigned_unit) -> None:
    """Hardware-offline alerts honor both status and assignment preference."""
    manager = AlertManager()
    assigned_unit.unit.status = "online"
    manager.check_hardware_offline_alerts(assigned_unit.unit)
    assert not Alert.objects.exists()

    assigned_unit.unit.status = "offline"
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification"
    ):
        manager.check_hardware_offline_alerts(assigned_unit.unit)

    alert = Alert.objects.get()
    assert alert.alert_type == "hardware_offline"
    assert alert.assignment == assigned_unit.assignment


@pytest.mark.django_db
def test_alert_state_transitions(assigned_unit) -> None:
    """Acknowledgement and resolution timestamps are persisted."""
    alert = AlertFactory(user=assigned_unit.user, channel=assigned_unit.channel)
    acknowledged = acknowledge_alert(alert.pk, user=assigned_unit.user)
    assert acknowledged.status == "acknowledged"
    assert acknowledged.acknowledged_at is not None

    resolved = resolve_alert(alert.pk, user=assigned_unit.user)
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None


@pytest.mark.django_db
def test_alert_state_transitions_are_owner_scoped() -> None:
    """Recipients and superusers can mutate alerts without exposing other users' rows."""
    owner = UserFactory()
    outsider = UserFactory()
    superuser = UserFactory(is_staff=True, is_superuser=True)
    alert = AlertFactory(user=owner)

    with pytest.raises(Alert.DoesNotExist):
        acknowledge_alert(alert.pk, user=outsider)
    with pytest.raises(Alert.DoesNotExist):
        resolve_alert(alert.pk, user=outsider)

    assert acknowledge_alert(alert.pk, user=owner).status == "acknowledged"
    assert resolve_alert(alert.pk, user=superuser).status == "resolved"


@pytest.mark.django_db
def test_alert_transitions_are_idempotent_and_cannot_regress_state() -> None:
    """Replayed actions preserve timestamps and terminal alerts cannot move backward."""
    owner = UserFactory()
    alert = AlertFactory(user=owner)

    acknowledged = acknowledge_alert(alert.pk, user=owner)
    acknowledged_at = acknowledged.acknowledged_at
    assert acknowledge_alert(alert.pk, user=owner).acknowledged_at == acknowledged_at

    resolved = resolve_alert(alert.pk, user=owner)
    resolved_at = resolved.resolved_at
    assert resolve_alert(alert.pk, user=owner).resolved_at == resolved_at

    with pytest.raises(ValueError, match="pending alerts"):
        acknowledge_alert(alert.pk, user=owner)
    failed = AlertFactory(user=owner, status="failed")
    with pytest.raises(ValueError, match="pending or acknowledged"):
        resolve_alert(failed.pk, user=owner)

    alert.refresh_from_db()
    assert alert.status == "resolved"
    assert alert.acknowledged_at == acknowledged_at
    assert alert.resolved_at == resolved_at


@pytest.mark.django_db
def test_alert_email_templates_use_current_hardware_relationships(assigned_unit) -> None:
    """Email rendering names the current chassis and assigned wireless unit."""
    alert = AlertFactory(
        user=assigned_unit.user,
        channel=assigned_unit.channel,
        assignment=assigned_unit.assignment,
    )
    context = {
        "alert": alert,
        "site_url": "https://micboard.example",
        "timestamp": timezone.now(),
    }

    html = render_to_string("micboard/emails/alert_notification.html", context)
    text = render_to_string("micboard/emails/alert_notification.txt", context)

    for message in (html, text):
        assert assigned_unit.channel.chassis.name in message
        assert assigned_unit.channel.chassis.ip in message
        assert assigned_unit.unit.name in message
