"""Behavioral branch coverage for small domain service modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.db import OperationalError
from django.test import override_settings

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.services.chargers.dashboard_service import ChargerDashboardService
from micboard.services.integrations.api_server_service import APIServerConnectionService
from micboard.services.locations.structure_service import prepare_building
from micboard.services.multitenancy.organization_service import (
    get_device_count,
    set_created_by,
)
from micboard.utils.exception_logging import sanitized_exception_info


def _server(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "pk": 7,
        "manufacturer": ManufacturerAPIServer.Manufacturer.SHURE,
        "base_url": "https://audio.example.test",
        "shared_key": "private-key",
        "status": ManufacturerAPIServer.Status.UNKNOWN,
        "status_message": "",
        "last_health_check": None,
        "save": Mock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_organization_service_counts_devices_and_records_creator() -> None:
    organization = SimpleNamespace(pk=9)
    with patch(
        "micboard.models.hardware.wireless_chassis.WirelessChassis.objects.filter"
    ) as chassis_filter:
        chassis_filter.return_value.count.return_value = 3
        assert get_device_count(organization) == 3
    chassis_filter.assert_called_once_with(location__building__organization_id=9)

    membership = SimpleNamespace(created_by=None)
    user = object()
    assert set_created_by(membership, user) is membership
    assert membership.created_by is user


def test_charger_dashboard_maps_complete_and_partial_assignments() -> None:
    user = object()
    photo = SimpleNamespace(url="/media/performer.jpg")
    chargers = [
        SimpleNamespace(
            pk=9,
            name="Stage charger",
            model="CHG-2",
            ip="192.0.2.20",
            _dashboard_slots=[
                SimpleNamespace(
                    slot_number=1,
                    occupied=True,
                    device_serial="UNIT-1",
                    device_model="TX-1",
                    battery_percent=None,
                    device_firmware_version="",
                    device_status="charging",
                    is_functional=True,
                ),
                SimpleNamespace(
                    slot_number=2,
                    occupied=True,
                    device_serial="UNIT-2",
                    device_model="TX-2",
                    battery_percent=80,
                    device_firmware_version="1.2",
                    device_status="updating",
                    is_functional=False,
                ),
            ],
        )
    ]
    charger_scope = MagicMock()
    (
        charger_scope.filter.return_value.order_by.return_value.__getitem__.return_value.prefetch_related.return_value
    ) = chargers
    assignments = [
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="UNIT-1"),
            performer=SimpleNamespace(name="One", title=None, photo=None),
        ),
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="UNIT-2"),
            performer=SimpleNamespace(name="Two", title="Lead", photo=photo),
        ),
    ]
    with (
        patch(
            "micboard.services.chargers.dashboard_service.Charger.objects.for_user",
            return_value=charger_scope,
        ),
        patch(
            "micboard.services.chargers.dashboard_service."
            "PerformerAssignmentService.get_preferred_active_assignments_for_serials",
            return_value=assignments,
        ) as preferred_assignments,
    ):
        result = ChargerDashboardService.get_snapshot(user=user)

    preferred_assignments.assert_called_once_with(
        user=user,
        serial_numbers={"UNIT-1", "UNIT-2"},
    )
    assert result.model_dump() == {
        "chargers": [
            {
                "id": 9,
                "name": "Stage charger",
                "model_name": "CHG-2",
                "ip_address": "192.0.2.20",
                "slots_truncated": False,
                "slot_limit": 32,
                "slots": [
                    {
                        "slot_number": 1,
                        "occupied": True,
                        "device_serial": "UNIT-1",
                        "device_model": "TX-1",
                        "battery_percent": None,
                        "device_firmware_version": "",
                        "device_status": "charging",
                        "is_functional": True,
                        "performer": {"name": "One", "title": "", "photo_url": None},
                    },
                    {
                        "slot_number": 2,
                        "occupied": True,
                        "device_serial": "UNIT-2",
                        "device_model": "TX-2",
                        "battery_percent": 80,
                        "device_firmware_version": "1.2",
                        "device_status": "updating",
                        "is_functional": False,
                        "performer": {
                            "name": "Two",
                            "title": "Lead",
                            "photo_url": "/media/performer.jpg",
                        },
                    },
                ],
            }
        ],
        "chargers_truncated": False,
        "charger_limit": 64,
    }


@pytest.mark.parametrize("country,has_domain", [(None, False), ("US", True)])
def test_prepare_building_skips_lookup_without_country_or_with_existing_domain(
    country: str | None,
    has_domain: bool,
) -> None:
    building = SimpleNamespace(country=country, regulatory_domain=object() if has_domain else None)
    with patch(
        "micboard.models.rf_coordination.compliance.RegulatoryDomain.objects.filter"
    ) as lookup:
        prepare_building(building)
    lookup.assert_not_called()


def test_prepare_building_assigns_matching_domain_and_tolerates_missing_or_unready_tables() -> None:
    domain = object()
    building = SimpleNamespace(country="us", regulatory_domain=None)
    with patch(
        "micboard.models.rf_coordination.compliance.RegulatoryDomain.objects.filter"
    ) as lookup:
        lookup.return_value.first.side_effect = [domain, None, OperationalError("not ready")]
        prepare_building(building)
        assert building.regulatory_domain is domain

        building.regulatory_domain = None
        prepare_building(building)
        assert building.regulatory_domain is None

        prepare_building(building)


@override_settings(MICBOARD_API_SERVER_ALLOWED_HOSTS=" Audio.Example.Test. , ")
def test_api_server_destination_accepts_normalized_string_allowlist() -> None:
    APIServerConnectionService.validate_destination("https://audio.example.test:8443")


def test_api_exception_context_redacts_original_message_and_preserves_traceback() -> None:
    try:
        raise ValueError("private-key")
    except ValueError as exc:
        exception_type, safe_exception, traceback = sanitized_exception_info(exc)

    assert exception_type is RuntimeError
    assert "private-key" not in str(safe_exception)
    assert "ValueError" in str(safe_exception)
    assert traceback is not None


@override_settings(MICBOARD_API_SERVER_ALLOWED_HOSTS=["audio.example.test"])
@patch("micboard.integrations.shure.client.ShureSystemAPIClient")
def test_fetch_shure_devices_normalizes_empty_vendor_response(client_class: MagicMock) -> None:
    client_class.return_value.__enter__.return_value.devices.get_devices.return_value = None

    assert (
        APIServerConnectionService.fetch_shure_devices(
            base_url="https://audio.example.test",
            shared_key="row-key",
        )
        == []
    )


def test_api_server_unsupported_manufacturer_paths_are_bounded() -> None:
    server = _server(manufacturer=ManufacturerAPIServer.Manufacturer.DANTE)
    with patch.object(APIServerConnectionService, "validate_destination") as validate:
        assert APIServerConnectionService.fetch_server_devices(server) is None
        APIServerConnectionService.test_connection(server)

    validate.assert_called_once_with(server.base_url)
    assert server.status == ManufacturerAPIServer.Status.UNKNOWN
    assert "not implemented" in server.status_message
    server.save.assert_called_once_with(update_fields=["status", "status_message", "updated_at"])


def test_api_server_connection_handles_none_and_records_sanitized_failures() -> None:
    server = _server()
    with patch.object(APIServerConnectionService, "fetch_server_devices", return_value=None):
        APIServerConnectionService.test_connection(server)
    server.save.assert_not_called()

    with patch.object(APIServerConnectionService, "test_connection") as test_connection:
        APIServerConnectionService.test_connection_and_record(server)
    test_connection.assert_called_once_with(server)

    secret = "private-key"
    with (
        patch.object(
            APIServerConnectionService,
            "test_connection",
            side_effect=RuntimeError(secret),
        ),
        patch(
            "micboard.services.integrations.api_server_service.timezone.now",
            return_value="now",
        ),
        patch("micboard.services.integrations.api_server_service.logger.exception") as logged,
    ):
        APIServerConnectionService.test_connection_and_record(server)

    assert server.status == ManufacturerAPIServer.Status.ERROR
    assert server.status_message == "Connection failed (RuntimeError)"
    assert server.last_health_check == "now"
    assert secret not in str(logged.call_args)
