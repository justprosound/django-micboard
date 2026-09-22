"""How a bulk chassis deletion is authorized and sequenced.

Deleting chassis in bulk has to lock the rows, register one discovery reconciliation per
affected manufacturer, and suppress the per-row delete hooks that reconciliation replaces.
All of that is a side effect, so none of it may happen before the request is authorized.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from django.core.exceptions import PermissionDenied

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_bulk_delete_service import ChassisBulkDeleteService
from tests.factories.base import UserFactory
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _manager() -> Any:
    """Build a staff user allowed to delete chassis."""
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def reconciliation(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Spy on the reconciliation boundary a rejected request must never reach.

    The ordering between authorization and this call is the behaviour under test: the admin
    action this service replaces scheduled reconciliation first and authorized afterwards,
    relying on a transaction rollback to undo it.
    """
    spy = Mock()
    monkeypatch.setattr(
        "micboard.services.core.hardware_post_save_hooks."
        "HardwarePostSaveHooks.handle_chassis_bulk_delete",
        spy,
    )
    return spy


def test_deleting_an_authorized_selection_removes_every_row(reconciliation: Mock) -> None:
    """An authorized bulk delete removes the whole selection and does reconcile."""
    manufacturer = ManufacturerFactory()
    first = WirelessChassisFactory(manufacturer=manufacturer)
    second = WirelessChassisFactory(manufacturer=manufacturer)

    result = ChassisBulkDeleteService.delete(
        chassis_ids=[first.pk, second.pk],
        requested_by=_manager(),
    )

    assert result.deleted_count == 2
    assert not WirelessChassis.objects.filter(pk__in=[first.pk, second.pk]).exists()
    reconciliation.assert_called_once()
    locked = reconciliation.call_args.kwargs["chassis_list"]
    assert sorted(chassis.pk for chassis in locked) == sorted([first.pk, second.pk])


def test_one_reconciliation_is_reported_per_affected_manufacturer() -> None:
    """Discovery reconciles each manufacturer once, not once per deleted chassis."""
    first_manufacturer = ManufacturerFactory()
    second_manufacturer = ManufacturerFactory()
    chassis_ids = [
        WirelessChassisFactory(manufacturer=first_manufacturer).pk,
        WirelessChassisFactory(manufacturer=first_manufacturer).pk,
        WirelessChassisFactory(manufacturer=second_manufacturer).pk,
    ]
    result = ChassisBulkDeleteService.delete(chassis_ids=chassis_ids, requested_by=_manager())

    assert result.deleted_count == 3
    assert result.reconciled_manufacturer_ids == sorted(
        [first_manufacturer.pk, second_manufacturer.pk]
    )


def test_an_unauthorized_request_is_rejected_before_any_side_effect(
    reconciliation: Mock,
) -> None:
    """A caller without delete permission never reaches the reconciliation boundary."""
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(manufacturer=manufacturer)
    read_only_user = UserFactory(is_staff=True)  # no delete_wirelesschassis permission

    with pytest.raises(PermissionDenied):
        ChassisBulkDeleteService.delete(
            chassis_ids=[chassis.pk],
            requested_by=read_only_user,
        )

    reconciliation.assert_not_called()
    assert WirelessChassis.objects.filter(pk=chassis.pk).exists()


def test_a_selection_mixing_manageable_and_foreign_rows_is_rejected_whole(
    reconciliation: Mock,
) -> None:
    """A partially permitted selection is refused rather than partially applied."""
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(manufacturer=manufacturer)
    missing_id = chassis.pk + 10_000

    with pytest.raises(PermissionDenied):
        ChassisBulkDeleteService.delete(
            chassis_ids=[chassis.pk, missing_id],
            requested_by=_manager(),
        )

    reconciliation.assert_not_called()
    assert WirelessChassis.objects.filter(pk=chassis.pk).exists()


def test_an_empty_selection_does_nothing_at_all(reconciliation: Mock) -> None:
    """An empty changelist selection is not an error and schedules no work."""
    result = ChassisBulkDeleteService.delete(chassis_ids=[], requested_by=_manager())

    assert result.deleted_count == 0
    assert result.reconciled_manufacturer_ids == []
    reconciliation.assert_not_called()
