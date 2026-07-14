"""Coverage for fair, bounded post-poll alert evaluation."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.poll_alert_service import (
    HARD_POLL_ALERT_MAX_UNITS,
    PollAlertService,
)
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessUnitFactory
from tests.factories.monitoring import PerformerAssignmentFactory


def _assigned_units(count: int):
    units = [WirelessUnitFactory() for _ in range(count)]
    for unit in units:
        assignment = PerformerAssignmentFactory(wireless_unit=unit)
        assignment.monitoring_group.users.add(UserFactory())
    return units


@pytest.mark.django_db
@override_settings(MICBOARD_POLL_ALERT_MAX_UNITS=2)
def test_alert_scan_rotates_through_inventory_and_wraps_fairly() -> None:
    """Repeated bounded scans advance past the first page instead of starving the tail."""
    units = _assigned_units(5)
    manufacturer = units[0].manufacturer
    for unit in units[1:]:
        unit.base_chassis.manufacturer = manufacturer
        unit.base_chassis.save(update_fields=["manufacturer"])
        unit.manufacturer = manufacturer
        unit.save(update_fields=["manufacturer"])
    cache.delete(PollAlertService._cursor_key(manufacturer.pk))
    cache.delete(PollAlertService._scope_cursor_key(manufacturer.pk))

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts"
        ) as offline,
        patch(
            "micboard.services.monitoring.poll_alert_service.check_transmitter_alerts"
        ) as transmitter,
    ):
        first = PollAlertService.evaluate_manufacturer(manufacturer)
        second = PollAlertService.evaluate_manufacturer(manufacturer)
        third = PollAlertService.evaluate_manufacturer(manufacturer)

    assert [item.args[0].pk for item in offline.call_args_list] == [
        units[0].pk,
        units[1].pk,
        units[2].pk,
        units[3].pk,
        units[4].pk,
        units[0].pk,
    ]
    assert [item.args[0] for item in transmitter.call_args_list] == [
        item.args[0] for item in offline.call_args_list
    ]
    for offline_call, transmitter_call in zip(
        offline.call_args_list,
        transmitter.call_args_list,
        strict=True,
    ):
        assert offline_call.kwargs["budget"] is transmitter_call.kwargs["budget"]
    assert first.truncated and second.truncated and third.truncated
    assert first.scanned == second.scanned == third.scanned == 2


@override_settings(MICBOARD_POLL_ALERT_MAX_UNITS=100_000)
def test_alert_scan_setting_cannot_exceed_hard_cap() -> None:
    """A host setting cannot remove the package-level workload ceiling."""
    assert PollAlertService._scan_limit() == HARD_POLL_ALERT_MAX_UNITS


@pytest.mark.parametrize("value", [True, object()])
def test_alert_scan_invalid_settings_use_the_safe_default(value: object) -> None:
    """Boolean and non-numeric scan limits cannot alter the workload ceiling."""
    with override_settings(MICBOARD_POLL_ALERT_MAX_UNITS=value):
        assert PollAlertService._scan_limit() == 100


def test_alert_scan_invalid_cursor_resets_to_start() -> None:
    """Malformed shared cursor values cannot alter scan ordering."""
    with patch("micboard.services.monitoring.poll_alert_service.cache.get", return_value=True):
        assert PollAlertService._read_cursor(1) == 0


@pytest.mark.django_db
@override_settings(MICBOARD_POLL_ALERT_MAX_UNITS=2)
def test_alert_scan_isolates_and_redacts_unit_failures(caplog) -> None:
    """One bad unit cannot stop the bounded scan or disclose exception details."""
    units = _assigned_units(2)
    manufacturer = units[0].manufacturer
    units[1].base_chassis.manufacturer = manufacturer
    units[1].base_chassis.save(update_fields=["manufacturer"])
    units[1].manufacturer = manufacturer
    units[1].save(update_fields=["manufacturer"])
    cache.delete(PollAlertService._cursor_key(manufacturer.pk))
    cache.delete(PollAlertService._scope_cursor_key(manufacturer.pk))
    secret = "private-alert-payload"

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts",
            side_effect=[RuntimeError(secret), None],
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service.check_transmitter_alerts"
        ) as transmitter,
    ):
        result = PollAlertService.evaluate_manufacturer(manufacturer)

    assert result.failed == 1
    transmitter.assert_called_once()
    assert transmitter.call_args.args == (units[1],)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.django_db
def test_alert_scan_continues_when_cursor_cache_fails(caplog) -> None:
    """Cache outages cannot suppress bounded alert evaluation or leak cache errors."""
    unit = _assigned_units(1)[0]
    secret = "cache-password"
    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.cache.get",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service.cache.set",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts"
        ) as offline,
        patch("micboard.services.monitoring.poll_alert_service.check_transmitter_alerts"),
    ):
        result = PollAlertService.evaluate_manufacturer(unit.manufacturer)

    offline.assert_called_once()
    assert offline.call_args.args == (unit,)
    assert result.scanned == 1
    assert secret not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize("revoked", ["user", "group"])
def test_alert_scan_excludes_units_without_active_fanout(assigned_unit, revoked: str) -> None:
    """Ineligible recipients do not consume the bounded unit scan."""
    if revoked == "user":
        assigned_unit.user.is_active = False
        assigned_unit.user.save(update_fields=["is_active"])
    else:
        assigned_unit.assignment.monitoring_group.is_active = False
        assigned_unit.assignment.monitoring_group.save(update_fields=["is_active"])

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts"
        ) as offline,
        patch(
            "micboard.services.monitoring.poll_alert_service.check_transmitter_alerts"
        ) as transmitter,
    ):
        result = PollAlertService.evaluate_manufacturer(assigned_unit.unit.manufacturer)

    assert result.scanned == 0
    assert result.assignments_evaluated == 0
    assert result.recipients_evaluated == 0
    offline.assert_not_called()
    transmitter.assert_not_called()


@pytest.mark.django_db
@override_settings(
    MICBOARD_POLL_ALERT_MAX_UNITS=1,
    MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS=10,
    MICBOARD_POLL_ALERT_MAX_RECIPIENTS=10,
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=2,
)
def test_poll_shares_one_exact_delivery_budget_across_alert_checks(assigned_unit) -> None:
    """Offline and transmitter evaluation cannot independently exceed the run ceiling."""
    assigned_unit.assignment.monitoring_group.users.add(UserFactory(), UserFactory())
    assigned_unit.unit.status = "offline"
    assigned_unit.unit.battery = 0
    assigned_unit.unit.rf_level = -90
    assigned_unit.unit.save(update_fields=["status", "battery", "rf_level"])
    cache.delete(PollAlertService._cursor_key(assigned_unit.unit.manufacturer_id))
    cache.delete(PollAlertService._scope_cursor_key(assigned_unit.unit.manufacturer_id))

    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email",
        return_value=True,
    ) as send_email:
        result = PollAlertService.evaluate_manufacturer(assigned_unit.unit.manufacturer)

    assert result.scanned == 1
    assert not result.units_truncated
    assert result.truncated
    assert result.delivery_attempts == 2
    assert result.deliveries_truncated
    assert result.assignments_evaluated == 2
    assert result.recipients_evaluated == 6
    assert Alert.objects.count() == 2
    assert send_email.call_count == 2


@pytest.mark.django_db
@override_settings(
    MICBOARD_POLL_ALERT_MAX_UNITS=1,
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=1,
)
def test_poll_rotates_first_access_to_an_exhaustible_scope_budget(assigned_unit) -> None:
    """Offline fanout cannot permanently starve transmitter checks across bounded scans."""
    manufacturer = assigned_unit.unit.manufacturer
    cache.delete(PollAlertService._cursor_key(manufacturer.pk))
    cache.delete(PollAlertService._scope_cursor_key(manufacturer.pk))
    claims: list[tuple[str, bool]] = []

    def claim_offline(_unit, *, budget) -> None:
        claims.append(("offline", budget.claim_delivery()))

    def claim_transmitter(_unit, *, budget) -> None:
        claims.append(("transmitter", budget.claim_delivery()))

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts",
            side_effect=claim_offline,
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service.check_transmitter_alerts",
            side_effect=claim_transmitter,
        ),
    ):
        first = PollAlertService.evaluate_manufacturer(manufacturer)
        second = PollAlertService.evaluate_manufacturer(manufacturer)

    assert claims == [
        ("offline", True),
        ("transmitter", False),
        ("transmitter", True),
        ("offline", False),
    ]
    assert first.delivery_attempts == second.delivery_attempts == 1
    assert first.deliveries_truncated and second.deliveries_truncated


@pytest.mark.django_db
@override_settings(
    MICBOARD_POLL_ALERT_MAX_UNITS=2,
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=1,
)
def test_exhausted_fanout_budget_advances_to_the_next_unit() -> None:
    """A bounded scope on the first unit cannot permanently starve later units."""
    units = _assigned_units(2)
    manufacturer = units[0].manufacturer
    units[1].base_chassis.manufacturer = manufacturer
    units[1].base_chassis.save(update_fields=["manufacturer"])
    units[1].manufacturer = manufacturer
    units[1].save(update_fields=["manufacturer"])
    cache.delete(PollAlertService._cursor_key(manufacturer.pk))
    cache.delete(PollAlertService._scope_cursor_key(manufacturer.pk))
    claims: list[tuple[str, int, bool]] = []

    def claim_offline(unit, *, budget) -> None:
        claims.append(("offline", unit.pk, budget.claim_delivery()))

    def claim_transmitter(unit, *, budget) -> None:
        claims.append(("transmitter", unit.pk, budget.claim_delivery()))

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts",
            side_effect=claim_offline,
        ),
        patch(
            "micboard.services.monitoring.poll_alert_service.check_transmitter_alerts",
            side_effect=claim_transmitter,
        ),
    ):
        first = PollAlertService.evaluate_manufacturer(manufacturer)
        second = PollAlertService.evaluate_manufacturer(manufacturer)

    assert claims == [
        ("offline", units[0].pk, True),
        ("transmitter", units[0].pk, False),
        ("transmitter", units[1].pk, True),
        ("offline", units[1].pk, False),
    ]
    assert first.scanned == second.scanned == 1
    assert first.units_truncated and second.units_truncated


@pytest.mark.django_db
@pytest.mark.parametrize("dimension", ["assignments", "recipients", "deliveries"])
@override_settings(
    MICBOARD_POLL_ALERT_MAX_UNITS=2,
    MICBOARD_POLL_ALERT_MAX_ASSIGNMENTS=1,
    MICBOARD_POLL_ALERT_MAX_RECIPIENTS=1,
    MICBOARD_POLL_ALERT_MAX_DELIVERIES=1,
)
def test_exact_fanout_cap_stops_before_advancing_past_the_next_unit(dimension: str) -> None:
    """Exact cap consumption resumes at, rather than after, the next eligible unit."""
    units = _assigned_units(2)
    manufacturer = units[0].manufacturer
    units[1].base_chassis.manufacturer = manufacturer
    units[1].base_chassis.save(update_fields=["manufacturer"])
    units[1].manufacturer = manufacturer
    units[1].save(update_fields=["manufacturer"])
    cache.delete(PollAlertService._cursor_key(manufacturer.pk))
    cache.delete(PollAlertService._scope_cursor_key(manufacturer.pk))
    evaluated: list[int] = []

    def consume_exact_cap(unit, *, budget) -> None:
        evaluated.append(unit.pk)
        if dimension == "assignments":
            budget.record_assignments(1, truncated=False)
        elif dimension == "recipients":
            budget.record_recipients(1, truncated=False)
        else:
            assert budget.claim_delivery()

    with (
        patch(
            "micboard.services.monitoring.poll_alert_service.check_hardware_offline_alerts",
            side_effect=consume_exact_cap,
        ),
        patch("micboard.services.monitoring.poll_alert_service.check_transmitter_alerts"),
    ):
        first = PollAlertService.evaluate_manufacturer(manufacturer)
        second = PollAlertService.evaluate_manufacturer(manufacturer)

    assert evaluated == [units[0].pk, units[1].pk]
    assert first.scanned == second.scanned == 1
    assert first.units_truncated and second.units_truncated
