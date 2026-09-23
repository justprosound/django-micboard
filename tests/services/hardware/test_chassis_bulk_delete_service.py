"""How a bulk chassis deletion is authorized and sequenced.

Deleting chassis in bulk has to lock the rows, register one discovery reconciliation per
affected manufacturer, and suppress the per-row delete hooks that reconciliation replaces.
All of that is a side effect, so none of it may happen before the request is authorized.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import override_settings

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_bulk_delete_service import ChassisBulkDeleteService
from micboard.services.shared.access_policy import tenant_role_access
from tests.factories.base import UserFactory
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

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


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_a_selection_reaching_into_another_tenant_is_refused(reconciliation: Mock) -> None:
    """A row that exists but belongs to another organization is outside the caller's scope.

    A non-existent primary key already fails the count check; this covers the case the
    authorization is actually for.
    """
    own_organization = OrganizationFactory()
    foreign_organization = OrganizationFactory()
    operator = UserFactory(is_staff=True, is_superuser=False)
    operator.user_permissions.add(
        Permission.objects.get(codename="delete_wirelesschassis"),
    )
    OrganizationMembershipFactory(
        user=operator,
        organization=own_organization,
        campus=None,
        role="admin",
    )
    own = WirelessChassisFactory(
        location=LocationFactory(building=BuildingFactory(organization_id=own_organization.pk)),
    )
    foreign = WirelessChassisFactory(
        location=LocationFactory(building=BuildingFactory(organization_id=foreign_organization.pk)),
    )

    with pytest.raises(PermissionDenied):
        ChassisBulkDeleteService.delete(
            chassis_ids=[own.pk, foreign.pk],
            requested_by=operator,
        )

    reconciliation.assert_not_called()
    assert WirelessChassis.objects.filter(pk__in=[own.pk, foreign.pk]).count() == 2

    # The same operator may delete their own organization's row, which is what makes the
    # rejection above about the foreign row rather than about the operator. The call is kept
    # out of the assert: `python -O` strips assert statements, which would drop the deletion.
    permitted = ChassisBulkDeleteService.delete(
        chassis_ids=[own.pk],
        requested_by=operator,
    )
    assert permitted.deleted_count == 1


def test_an_empty_selection_does_nothing_at_all(reconciliation: Mock) -> None:
    """An empty changelist selection is not an error and schedules no work."""
    result = ChassisBulkDeleteService.delete(chassis_ids=[], requested_by=_manager())

    assert result.deleted_count == 0
    assert result.reconciled_manufacturer_ids == []
    reconciliation.assert_not_called()


def test_scope_is_rechecked_while_the_rows_are_locked(reconciliation: Mock) -> None:
    """Authorizing before the lock leaves a window where a row can leave the caller's scope.

    A concurrent location change between the check and the lock would otherwise be deleted
    anyway, because the delete used the originally selected identifiers.
    """
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisFactory(manufacturer=manufacturer)
    calls: list[int] = []
    real = tenant_role_access.scope_manageable_queryset

    def narrow_after_the_first_check(queryset, *, user):
        calls.append(1)
        if len(calls) == 1:
            return real(queryset, user=user)
        return queryset.none()

    with (
        patch.object(
            tenant_role_access,
            "scope_manageable_queryset",
            side_effect=narrow_after_the_first_check,
        ),
        pytest.raises(PermissionDenied),
    ):
        ChassisBulkDeleteService.delete(
            chassis_ids=[chassis.pk],
            requested_by=_manager(),
        )

    assert len(calls) >= 2, "authorization must be re-checked after locking"
    reconciliation.assert_not_called()
    assert WirelessChassis.objects.filter(pk=chassis.pk).exists()
