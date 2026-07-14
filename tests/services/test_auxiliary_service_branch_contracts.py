"""Behavioral branch coverage for small domain service modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.db import OperationalError
from django.test import override_settings

import pytest

from micboard.models.integrations import ManufacturerAPIServer
from micboard.multitenancy import is_msp_enabled, is_multisite_enabled
from micboard.services.chargers.charger_display_service import get_charging_stations_data
from micboard.services.integrations.api_server_service import APIServerConnectionService
from micboard.services.kiosk import KioskService
from micboard.services.locations.structure_service import prepare_building
from micboard.services.multitenancy.organization_service import (
    get_device_count,
    is_at_device_limit,
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


def test_organization_service_counts_limits_and_records_creator() -> None:
    organization = SimpleNamespace(pk=9, max_devices=None)
    with patch(
        "micboard.models.hardware.wireless_chassis.WirelessChassis.objects.filter"
    ) as chassis_filter:
        chassis_filter.return_value.count.return_value = 3
        assert get_device_count(organization) == 3
    chassis_filter.assert_called_once_with(location__building__organization_id=9)
    assert not is_at_device_limit(organization)

    organization.max_devices = 3
    with patch(
        "micboard.services.multitenancy.organization_service.get_device_count",
        side_effect=[2, 3],
    ):
        assert not is_at_device_limit(organization)
        assert is_at_device_limit(organization)

    membership = SimpleNamespace(created_by=None)
    user = object()
    assert set_created_by(membership, user) is membership
    assert membership.created_by is user


def test_kiosk_charger_dashboard_maps_complete_and_partial_assignments() -> None:
    user = object()
    chargers = [object()]
    charger_scope = MagicMock()
    charger_scope.filter.return_value.prefetch_related.return_value.order_by.return_value = chargers
    assignment_scope = MagicMock()
    photo = SimpleNamespace(url="/media/performer.jpg")
    assignments = [
        SimpleNamespace(wireless_unit=None),
        SimpleNamespace(wireless_unit=SimpleNamespace(serial_number="")),
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="UNIT-1"),
            performer=SimpleNamespace(name="One", title=None, photo=None),
        ),
        SimpleNamespace(
            wireless_unit=SimpleNamespace(serial_number="UNIT-2"),
            performer=SimpleNamespace(name="Two", title="Lead", photo=photo),
        ),
    ]
    assignment_scope.filter.return_value.select_related.return_value = assignments
    with (
        patch("micboard.services.kiosk.Charger.objects.for_user", return_value=charger_scope),
        patch(
            "micboard.services.kiosk.PerformerAssignment.objects.for_user",
            return_value=assignment_scope,
        ),
    ):
        result = KioskService.get_charger_dashboard_data(user=user)

    assert result["chargers"] is chargers
    assert result["serial_to_performer"] == {
        "UNIT-1": {"name": "One", "title": "", "photo_url": None},
        "UNIT-2": {"name": "Two", "title": "Lead", "photo_url": "/media/performer.jpg"},
    }


def test_kiosk_section_delegates_tenant_scoped_assignment_lookup() -> None:
    user = object()
    with patch(
        "micboard.services.core.charger_assignment.ChargerAssignmentService.get_wall_section_performers",
        return_value=["performer"],
    ) as get_performers:
        result = KioskService.get_section_data(section_id=5, user=user)

    assert result == {"performers": ["performer"]}
    get_performers.assert_called_once_with(5, user=user)


def test_charger_display_serializes_occupied_empty_and_model_specific_slots() -> None:
    slots = [
        SimpleNamespace(
            slot_number=1,
            occupied=True,
            device_model="ulxd1",
            battery_percent=None,
            device_status="charging",
        ),
        SimpleNamespace(
            slot_number=2,
            occupied=True,
            device_model=None,
            battery_percent=65,
            device_status="ready",
        ),
        SimpleNamespace(slot_number=3, occupied=False),
    ]
    chargers = [
        SimpleNamespace(
            serial_number="CH-1",
            name="",
            status="offline",
            slots=SimpleNamespace(all=Mock(return_value=slots)),
        )
    ]
    scope = MagicMock()
    scope.filter.return_value.order_by.return_value.prefetch_related.return_value = chargers
    with patch(
        "micboard.services.chargers.charger_display_service.Charger.objects.for_user",
        return_value=scope,
    ):
        result = get_charging_stations_data(user=object())

    assert result[0]["name"] == "Charger CH-1"
    assert result[0]["status"] == "offline"
    assert result[0]["slots"][0]["image"].endswith("ulxd1_wl185.svg")
    assert result[0]["slots"][0]["battery_level"] == 0
    assert result[0]["slots"][1]["mic_name"] == "Slot 2"
    assert result[0]["slots"][2] == {
        "slot_number": 3,
        "image": None,
        "mic_name": "Empty",
        "battery_level": 0,
        "charging": False,
    }


@pytest.mark.parametrize("country,has_domain", [(None, False), ("US", True)])
def test_prepare_building_skips_lookup_without_country_or_with_existing_domain(
    country: str | None,
    has_domain: bool,
) -> None:
    building = SimpleNamespace(country=country, regulatory_domain=object() if has_domain else None)
    with patch("micboard.models.rf_coordination.RegulatoryDomain.objects.filter") as lookup:
        prepare_building(building)
    lookup.assert_not_called()


def test_prepare_building_assigns_matching_domain_and_tolerates_missing_or_unready_tables() -> None:
    domain = object()
    building = SimpleNamespace(country="us", regulatory_domain=None)
    with patch("micboard.models.rf_coordination.RegulatoryDomain.objects.filter") as lookup:
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


@pytest.mark.parametrize(
    ("function", "setting_name"),
    [(is_msp_enabled, "MICBOARD_MSP_ENABLED"), (is_multisite_enabled, "MICBOARD_MULTI_SITE_MODE")],
)
def test_multitenancy_feature_helpers_return_flags_and_fail_closed(
    function: object,
    setting_name: str,
) -> None:
    enabled_settings = SimpleNamespace(**{setting_name: True})
    with patch("django.conf.settings", enabled_settings):
        assert function() is True

    class BrokenSettings:
        def __getattr__(self, name: str) -> object:
            raise RuntimeError(name)

    with patch("django.conf.settings", BrokenSettings()):
        assert function() is False
