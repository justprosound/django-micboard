"""Contracts for the authoritative WirelessChassis persistence seam."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from micboard.exceptions import OrganizationDeviceQuotaExceededError
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.multitenancy.models import Organization
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.multitenancy import OrganizationFactory


def _database_write(*, number: int, location: object | None = None) -> WirelessChassisWrite:
    """Build a valid, side-effect-light chassis write for database boundary tests."""
    return WirelessChassisWrite(
        api_device_id=f"quota-device-{number}",
        ip=f"192.0.2.{number}",
        role="receiver",
        max_channels=0,
        location=location,
    )


@pytest.mark.parametrize(
    ("manufacturer", "write", "message"),
    [
        (None, WirelessChassisWrite(api_device_id="device", ip="192.0.2.10"), "manufacturer"),
        (object(), WirelessChassisWrite(ip="192.0.2.10"), "api_device_id and ip"),
        (object(), WirelessChassisWrite(api_device_id="device"), "api_device_id and ip"),
    ],
)
def test_create_requires_complete_external_identity(
    manufacturer: object | None,
    write: WirelessChassisWrite,
    message: str,
) -> None:
    """Incomplete write DTOs fail before reaching the model manager."""
    with pytest.raises(ValueError, match=message):
        WirelessChassisPersistenceService.create(
            manufacturer=manufacturer,
            write=write,
        )


def test_quota_resolution_noops_when_multitenancy_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reusable core app cannot require the optional MSP model registry."""
    monkeypatch.setattr(
        "micboard.services.hardware.wireless_chassis_persistence_service.apps.is_installed",
        lambda _app_name: False,
    )

    assert (
        WirelessChassisPersistenceService._organization_id_for_values(
            {"location": SimpleNamespace(pk=1)},
            using="default",
        )
        is None
    )


def test_create_uses_requested_database_and_only_explicit_fields() -> None:
    """Creation forwards a validated field set through the selected manager."""
    manufacturer = object()
    created = object()
    database_manager = Mock()
    database_manager.create.return_value = created

    with patch.object(
        WirelessChassis.objects,
        "db_manager",
        return_value=database_manager,
    ) as db_manager:
        result = WirelessChassisPersistenceService.create(
            manufacturer=manufacturer,
            write=WirelessChassisWrite(
                api_device_id="device-10",
                ip="192.0.2.10",
                name="Receiver 10",
            ),
            using="inventory",
        )

    assert result is created
    db_manager.assert_called_once_with("inventory")
    database_manager.create.assert_called_once_with(
        manufacturer=manufacturer,
        api_device_id="device-10",
        ip="192.0.2.10",
        name="Receiver 10",
    )


def test_update_distinguishes_explicit_empty_values_and_full_saves() -> None:
    """Partial writes preserve update fields; approval can request its legacy full save."""
    chassis = SimpleNamespace(name="Old", location=object(), save=Mock())

    assert (
        WirelessChassisPersistenceService.update(
            chassis=chassis,
            write=WirelessChassisWrite(name="", location=None),
            using="default",
        )
        is chassis
    )
    assert chassis.name == ""
    assert chassis.location is None
    chassis.save.assert_called_once_with(using="default", update_fields=["name", "location"])

    chassis.save.reset_mock()
    WirelessChassisPersistenceService.update(
        chassis=chassis,
        write=WirelessChassisWrite(status="online"),
        using="inventory",
        save_all_fields=True,
    )
    chassis.save.assert_called_once_with(using="inventory")


def test_update_skips_empty_field_sets() -> None:
    """An empty DTO cannot trigger lifecycle hooks or a redundant database write."""
    chassis = SimpleNamespace(save=Mock())

    assert (
        WirelessChassisPersistenceService.update(
            chassis=chassis,
            write=WirelessChassisWrite(),
        )
        is chassis
    )
    chassis.save.assert_not_called()


def test_upsert_keeps_lookup_identity_out_of_update_defaults() -> None:
    """Manufacturer and API identity remain lookup keys rather than mutable defaults."""
    manufacturer = object()
    persisted = object()
    manager = Mock()
    manager.db_manager.return_value = manager
    manager.update_or_create.return_value = (persisted, True)
    defaults = WirelessChassisWrite(ip="192.0.2.11", name="Receiver 11")

    with patch.object(WirelessChassis, "objects", manager):
        result = WirelessChassisPersistenceService.upsert(
            manufacturer=manufacturer,
            api_device_id="device-11",
            defaults=defaults,
            create_defaults=defaults.model_copy(update={"status": "online"}),
        )

    assert result == (persisted, True)
    manager.update_or_create.assert_called_once_with(
        api_device_id="device-11",
        manufacturer=manufacturer,
        defaults={"ip": "192.0.2.11", "name": "Receiver 11"},
        create_defaults={
            "ip": "192.0.2.11",
            "name": "Receiver 11",
            "status": "online",
        },
    )


def test_upsert_requires_external_identity() -> None:
    """An empty manufacturer identity cannot reach the model manager."""
    with pytest.raises(ValueError, match="api_device_id"):
        WirelessChassisPersistenceService.upsert(
            manufacturer=object(),
            api_device_id="",
            defaults=WirelessChassisWrite(ip="192.0.2.12"),
        )


@pytest.mark.django_db
def test_finite_organization_quota_locks_owner_and_rejects_only_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The organization row serializes count-and-create and blocks the next slot."""
    organization = OrganizationFactory(max_devices=1)
    location = LocationFactory(building=BuildingFactory(organization_id=organization.pk))
    manufacturer = ManufacturerFactory()
    locked_models: list[type[object]] = []

    from django.db.models import QuerySet

    select_for_update = QuerySet.select_for_update

    def record_lock(queryset, *args, **kwargs):
        locked_models.append(queryset.model)
        return select_for_update(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", record_lock)

    created = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=21, location=location),
    )

    with pytest.raises(OrganizationDeviceQuotaExceededError) as raised:
        WirelessChassisPersistenceService.create(
            manufacturer=manufacturer,
            write=_database_write(number=22, location=location),
        )

    assert created.location == location
    assert Organization in locked_models
    assert raised.value.code == "ORGANIZATION_DEVICE_QUOTA_EXCEEDED"
    assert raised.value.details == {
        "organization_id": organization.pk,
        "max_devices": 1,
        "current_devices": 1,
    }
    assert (
        WirelessChassis.objects.filter(location__building__organization_id=organization.pk).count()
        == 1
    )


@pytest.mark.django_db
def test_quota_counts_only_the_resolved_organization() -> None:
    """A full sibling tenant cannot consume another organization's slot."""
    full_organization = OrganizationFactory(max_devices=1)
    available_organization = OrganizationFactory(max_devices=1)
    full_location = LocationFactory(building=BuildingFactory(organization_id=full_organization.pk))
    available_location = LocationFactory(
        building=BuildingFactory(organization_id=available_organization.pk)
    )
    manufacturer = ManufacturerFactory()
    WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=23, location=full_location),
    )

    created = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=24, location=available_location),
    )

    assert created.location == available_location


@pytest.mark.django_db
def test_locationless_platform_inventory_is_explicitly_outside_organization_quota() -> None:
    """Without a location ownership path, discovery inventory remains unscoped."""
    organization = OrganizationFactory(max_devices=1)
    location = LocationFactory(building=BuildingFactory(organization_id=organization.pk))
    manufacturer = ManufacturerFactory()
    WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=25, location=location),
    )

    platform_chassis = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=26),
    )

    assert platform_chassis.location is None
    assert (
        WirelessChassis.objects.filter(location__building__organization_id=organization.pk).count()
        == 1
    )


@pytest.mark.django_db
def test_only_existing_organizations_with_finite_quotas_are_enforced() -> None:
    """Unowned, orphaned, and explicitly unlimited locations remain creatable."""
    manufacturer = ManufacturerFactory()
    unowned_location = LocationFactory(building=BuildingFactory(organization_id=None))
    orphaned_location = LocationFactory(building=BuildingFactory(organization_id=999_999))
    unlimited_organization = OrganizationFactory(max_devices=None)
    unlimited_location = LocationFactory(
        building=BuildingFactory(organization_id=unlimited_organization.pk)
    )

    for number, location in (
        (29, unowned_location),
        (30, orphaned_location),
        (31, unlimited_location),
        (32, unlimited_location),
    ):
        WirelessChassisPersistenceService.create(
            manufacturer=manufacturer,
            write=_database_write(number=number, location=location),
        )

    assert WirelessChassis.objects.filter(location=unlimited_location).count() == 2


@pytest.mark.django_db
def test_upsert_at_quota_updates_existing_but_rejects_new_identity() -> None:
    """Quota enforcement applies to the create branch, never an existing-row update."""
    organization = OrganizationFactory(max_devices=1)
    location = LocationFactory(building=BuildingFactory(organization_id=organization.pk))
    manufacturer = ManufacturerFactory()
    existing_write = _database_write(number=27, location=location)
    existing = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=existing_write,
    )
    defaults = WirelessChassisWrite(
        ip=str(existing.ip),
        role="receiver",
        max_channels=0,
        location=location,
        name="Updated at quota",
    )

    updated, created = WirelessChassisPersistenceService.upsert(
        manufacturer=manufacturer,
        api_device_id=existing.api_device_id,
        defaults=defaults,
    )

    assert created is False
    assert updated.name == "Updated at quota"
    with pytest.raises(OrganizationDeviceQuotaExceededError):
        WirelessChassisPersistenceService.upsert(
            manufacturer=manufacturer,
            api_device_id="quota-device-28",
            defaults=WirelessChassisWrite(
                ip="192.0.2.28",
                role="receiver",
                max_channels=0,
                location=location,
            ),
        )


@pytest.mark.django_db
def test_update_rejects_transfer_into_full_organization() -> None:
    """Changing location cannot bypass the destination organization's finite quota."""
    source = OrganizationFactory(max_devices=None)
    destination = OrganizationFactory(max_devices=1)
    source_location = LocationFactory(building=BuildingFactory(organization_id=source.pk))
    destination_location = LocationFactory(building=BuildingFactory(organization_id=destination.pk))
    manufacturer = ManufacturerFactory()
    chassis = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=33, location=source_location),
    )
    WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=34, location=destination_location),
    )

    with pytest.raises(OrganizationDeviceQuotaExceededError):
        WirelessChassisPersistenceService.update(
            chassis=chassis,
            write=WirelessChassisWrite(location=destination_location),
        )

    chassis.refresh_from_db()
    assert chassis.location == source_location


@pytest.mark.django_db
def test_upsert_rejects_transfer_but_allows_same_owner_update_at_quota() -> None:
    """Upsert updates consume quota only when they enter a different organization."""
    source = OrganizationFactory(max_devices=1)
    destination = OrganizationFactory(max_devices=1)
    source_location = LocationFactory(building=BuildingFactory(organization_id=source.pk))
    destination_location = LocationFactory(building=BuildingFactory(organization_id=destination.pk))
    manufacturer = ManufacturerFactory()
    moving = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=35, location=source_location),
    )
    staying = WirelessChassisPersistenceService.create(
        manufacturer=manufacturer,
        write=_database_write(number=36, location=destination_location),
    )

    same_owner, created = WirelessChassisPersistenceService.upsert(
        manufacturer=manufacturer,
        api_device_id=staying.api_device_id,
        defaults=WirelessChassisWrite(
            ip=str(staying.ip),
            location=destination_location,
            name="Same owner update",
        ),
    )

    assert created is False
    assert same_owner.name == "Same owner update"
    with pytest.raises(OrganizationDeviceQuotaExceededError):
        WirelessChassisPersistenceService.upsert(
            manufacturer=manufacturer,
            api_device_id=moving.api_device_id,
            defaults=WirelessChassisWrite(
                ip=str(moving.ip),
                location=destination_location,
            ),
        )

    moving.refresh_from_db()
    assert moving.location == source_location
