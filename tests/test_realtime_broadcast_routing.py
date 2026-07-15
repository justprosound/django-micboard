"""Tenant-routing coverage for realtime event producers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import override_settings

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location
from micboard.multitenancy.models import Campus, Organization
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.notification.realtime_routing_service import (
    GLOBAL_UPDATES_GROUP,
    RealtimeRoutingService,
    campus_updates_group,
    organization_updates_group,
    site_updates_group,
)


def _configured_layer(get_channel_layer: MagicMock, async_to_sync: MagicMock) -> Mock:
    """Configure a mocked channel layer and return its synchronous sender."""
    get_channel_layer.return_value = SimpleNamespace(group_send=Mock())
    sender = Mock()
    async_to_sync.return_value = sender
    return sender


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
@patch.object(RealtimeRoutingService, "chassis_site_ids", return_value={1: 1, 2: 2})
@patch("micboard.services.notification.broadcast_service.async_to_sync")
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_multisite_device_updates_are_partitioned_by_site(
    get_channel_layer: MagicMock,
    async_to_sync: MagicMock,
    _chassis_site_ids: MagicMock,
) -> None:
    sender = _configured_layer(get_channel_layer, async_to_sync)

    BroadcastService.broadcast_device_update(
        manufacturer=SimpleNamespace(code="vendor"),
        data={
            "receivers": [
                {"id": 1, "name": "Current"},
                {"id": 2, "name": "Other"},
                {"id": 3, "name": "Unscoped"},
            ]
        },
    )

    routed = dict(item.args for item in sender.call_args_list)
    assert routed[site_updates_group(1)]["data"]["receivers"] == [{"id": 1, "name": "Current"}]
    assert routed[site_updates_group(2)]["data"]["receivers"] == [{"id": 2, "name": "Other"}]
    assert GLOBAL_UPDATES_GROUP not in routed


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
@patch.object(RealtimeRoutingService, "hardware_site_id", return_value=2)
@patch("micboard.services.notification.broadcast_service.async_to_sync")
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_multisite_device_status_routes_to_hardware_site(
    get_channel_layer: MagicMock,
    async_to_sync: MagicMock,
    _hardware_site_id: MagicMock,
) -> None:
    sender = _configured_layer(get_channel_layer, async_to_sync)

    BroadcastService.broadcast_device_status(
        service_code="vendor",
        device_id=9,
        device_type="WirelessChassis",
        status="online",
        is_active=True,
    )

    assert sender.call_args.args[0] == site_updates_group(2)


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(
    RealtimeRoutingService,
    "chassis_tenant_scopes",
    return_value={1: (10, None), 2: (20, 30)},
)
@patch("micboard.services.notification.broadcast_service.async_to_sync")
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_device_updates_are_partitioned_without_cross_tenant_data(
    get_channel_layer: MagicMock,
    async_to_sync: MagicMock,
    _chassis_tenant_scopes: MagicMock,
) -> None:
    sender = _configured_layer(get_channel_layer, async_to_sync)
    manufacturer = SimpleNamespace(code="vendor")

    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer,
        data={
            "receivers": [
                {"id": 1, "name": "Organization One"},
                {"id": 2, "name": "Campus Two"},
                {"id": 3, "name": "Unscoped"},
            ]
        },
    )

    routed = dict(item.args for item in sender.call_args_list)
    assert set(routed) == {
        organization_updates_group(10),
        organization_updates_group(20),
        campus_updates_group(20, 30),
    }
    assert routed[organization_updates_group(10)]["data"]["receivers"] == [
        {"id": 1, "name": "Organization One"}
    ]
    expected_campus_receivers = [{"id": 2, "name": "Campus Two"}]
    assert routed[organization_updates_group(20)]["data"]["receivers"] == (
        expected_campus_receivers
    )
    assert routed[campus_updates_group(20, 30)]["data"]["receivers"] == (expected_campus_receivers)
    assert GLOBAL_UPDATES_GROUP not in routed


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(
    RealtimeRoutingService,
    "manufacturer_tenant_scopes",
    return_value=((10, None), (20, 30)),
)
@patch("micboard.services.notification.broadcast_service.async_to_sync")
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_manufacturer_health_routes_only_to_owning_tenants(
    get_channel_layer: MagicMock,
    async_to_sync: MagicMock,
    _manufacturer_tenant_scopes: MagicMock,
) -> None:
    sender = _configured_layer(get_channel_layer, async_to_sync)
    manufacturer = SimpleNamespace(pk=7, code="vendor")

    BroadcastService.broadcast_api_health(
        manufacturer=manufacturer,
        health_data={"status": "healthy"},
    )

    assert [item.args[0] for item in sender.call_args_list] == [
        organization_updates_group(10),
        organization_updates_group(20),
        campus_updates_group(20, 30),
    ]
    assert GLOBAL_UPDATES_GROUP not in {item.args[0] for item in sender.call_args_list}


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(RealtimeRoutingService, "hardware_tenant_scope", return_value=None)
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_unscoped_device_status_does_not_fall_back_to_global(
    get_channel_layer: MagicMock,
    _hardware_tenant_scope: MagicMock,
) -> None:
    BroadcastService.broadcast_device_status(
        service_code="vendor",
        device_id=99,
        device_type="WirelessChassis",
        status="online",
        is_active=True,
    )

    get_channel_layer.assert_not_called()


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_unknown_device_type_fails_closed(get_channel_layer: MagicMock) -> None:
    BroadcastService.broadcast_device_status(
        service_code="vendor",
        device_id=1,
        device_type="Unknown",
        status="online",
        is_active=True,
    )

    get_channel_layer.assert_not_called()


@pytest.mark.django_db
def test_chassis_route_is_derived_from_its_building() -> None:
    organization = Organization.objects.create(name="Tenant", slug="tenant")
    campus = Campus.objects.create(
        organization=organization,
        name="Main Campus",
        slug="main",
    )
    building = Building.objects.create(
        name="Tenant Building",
        organization_id=organization.pk,
        campus_id=campus.pk,
    )
    location = Location.objects.create(name="Rack", building=building)
    manufacturer = Manufacturer.objects.create(name="Vendor", code="vendor")
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="device-1",
        role="receiver",
        ip="192.0.2.10",
        location=location,
    )

    assert RealtimeRoutingService.chassis_tenant_scopes((chassis.pk,))[chassis.pk] == (
        organization.pk,
        campus.pk,
    )


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True)
@patch("micboard.services.notification.broadcast_service.async_to_sync")
@patch("micboard.services.notification.broadcast_service.get_channel_layer")
def test_wireless_unit_id_collision_routes_via_base_chassis(
    get_channel_layer: MagicMock,
    async_to_sync: MagicMock,
) -> None:
    first_organization = Organization.objects.create(name="First Tenant", slug="first")
    second_organization = Organization.objects.create(name="Second Tenant", slug="second")
    first_building = Building.objects.create(
        name="First Building",
        organization_id=first_organization.pk,
    )
    second_building = Building.objects.create(
        name="Second Building",
        organization_id=second_organization.pk,
    )
    first_location = Location.objects.create(name="First Rack", building=first_building)
    second_location = Location.objects.create(name="Second Rack", building=second_building)
    manufacturer = Manufacturer.objects.create(name="Collision Vendor", code="collision")
    first_chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="first-chassis",
        role="receiver",
        ip="192.0.2.20",
        location=first_location,
    )
    second_chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="second-chassis",
        role="receiver",
        ip="192.0.2.21",
        location=second_location,
    )
    second_tenant_unit = WirelessUnit.objects.create(
        base_chassis=second_chassis,
        manufacturer=manufacturer,
        slot=1,
    )
    assert first_chassis.pk == second_tenant_unit.pk
    sender = _configured_layer(get_channel_layer, async_to_sync)

    BroadcastService.broadcast_device_status(
        service_code=manufacturer.code,
        device_id=second_tenant_unit.pk,
        device_type="WirelessUnit",
        status="online",
        is_active=True,
    )

    routed_groups = [item.args[0] for item in sender.call_args_list]
    assert routed_groups == [organization_updates_group(second_organization.pk)]
    assert organization_updates_group(first_organization.pk) not in routed_groups
