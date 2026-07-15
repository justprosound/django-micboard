"""Unit tests for chassis_regulatory_service functions.

Tests the regulatory domain resolution, band plan coverage checking, and
regulatory status reporting extracted from WirelessChassis per ADR-002.
"""

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Building, Location
from micboard.models.rf_coordination.compliance import (
    FrequencyBand,
    RegulatoryDomain,
)
from micboard.services.hardware.chassis_regulatory_service import (
    get_band_plan_regulatory_status,
    get_needs_band_plan_regulatory_update,
    has_band_plan_regulatory_coverage,
)
from micboard.services.hardware.rf_channel_service import get_regulatory_domain_for_location


@pytest.fixture
def manufacturer(db):
    return Manufacturer.objects.create(name="Shure", code="shure")


@pytest.fixture
def regulatory_domain(db):
    return RegulatoryDomain.objects.create(
        code="FCC",
        name="Federal Communications Commission",
        country_code="US",
        min_frequency_mhz=470.0,
        max_frequency_mhz=608.0,
    )


@pytest.fixture
def building(db, regulatory_domain):
    return Building.objects.create(
        name="Test Building",
        country="US",
        regulatory_domain=regulatory_domain,
    )


@pytest.fixture
def location(db, building):
    return Location.objects.create(
        building=building,
        name="Test Location",
    )


@pytest.fixture
def chassis_with_band_plan(db, manufacturer, location):
    return WirelessChassis.objects.create(
        manufacturer=manufacturer,
        name="Test Chassis",
        model="ULXD4Q",
        ip="192.168.1.100",
        status="online",
        location=location,
        band_plan_min_mhz=470.0,
        band_plan_max_mhz=534.0,
        band_plan_name="G50 (470-534 MHz)",
    )


@pytest.fixture
def chassis_no_band_plan(db, manufacturer, location):
    return WirelessChassis.objects.create(
        manufacturer=manufacturer,
        name="No Band Plan Chassis",
        model="ULXD4Q",
        ip="192.168.1.101",
        status="online",
        location=location,
    )


@pytest.fixture
def chassis_no_location(db, manufacturer):
    return WirelessChassis.objects.create(
        manufacturer=manufacturer,
        name="No Location Chassis",
        model="ULXD4Q",
        ip="192.168.1.102",
        status="online",
    )


@pytest.fixture
def frequency_band(db, regulatory_domain):
    return FrequencyBand.objects.create(
        regulatory_domain=regulatory_domain,
        name="UHF Band 1",
        start_frequency_mhz=470.0,
        end_frequency_mhz=534.0,
        band_type="allowed",
    )


class TestGetRegulatoryDomain:
    def test_with_location_and_domain(self, chassis_with_band_plan, regulatory_domain):
        domain = get_regulatory_domain_for_location(chassis_with_band_plan.location)
        assert domain is not None
        assert domain.code == "FCC"

    def test_no_location(self, chassis_no_location):
        domain = get_regulatory_domain_for_location(chassis_no_location.location)
        assert domain is None

    def test_location_has_no_domain(self, db, manufacturer):
        building = Building.objects.create(name="No Domain Building", country="XX")
        loc = Location.objects.create(building=building, name="Unknown Loc")
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="No Domain Chassis",
            model="ULXD4Q",
            ip="192.168.1.103",
            status="online",
            location=loc,
        )
        domain = get_regulatory_domain_for_location(chassis.location)
        assert domain is None

    def test_location_with_country_lookup(self, db, manufacturer, regulatory_domain):
        building = Building.objects.create(name="US Building", country="US")
        loc = Location.objects.create(building=building, name="US Loc")
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="US Chassis",
            model="ULXD4Q",
            ip="192.168.1.104",
            status="online",
            location=loc,
        )
        domain = get_regulatory_domain_for_location(chassis.location)
        assert domain == regulatory_domain


class TestHasBandPlanRegulatoryCoverage:
    def test_no_band_plan(self, chassis_no_band_plan):
        assert not has_band_plan_regulatory_coverage(chassis_no_band_plan)

    def test_no_location(self, chassis_no_location):
        chassis_no_location.band_plan_min_mhz = 470.0
        chassis_no_location.band_plan_max_mhz = 534.0
        assert not has_band_plan_regulatory_coverage(chassis_no_location)

    def test_coverage_via_domain_bounds(self, chassis_with_band_plan, regulatory_domain):
        regulatory_domain.min_frequency_mhz = 470.0
        regulatory_domain.max_frequency_mhz = 534.0
        regulatory_domain.save()
        assert has_band_plan_regulatory_coverage(chassis_with_band_plan)

    def test_coverage_via_frequency_bands(self, chassis_with_band_plan, frequency_band):
        assert has_band_plan_regulatory_coverage(chassis_with_band_plan)

    def test_no_coverage_outside_domain(self, db, manufacturer, location, regulatory_domain):
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="Out of Range",
            model="ULXD4Q",
            ip="192.168.1.105",
            status="online",
            location=location,
            band_plan_min_mhz=900.0,
            band_plan_max_mhz=1000.0,
        )
        assert not has_band_plan_regulatory_coverage(chassis)


class TestGetNeedsBandPlanRegulatoryUpdate:
    def test_offline_chassis_no_update_needed(self, chassis_with_band_plan):
        chassis_with_band_plan.status = "offline"
        assert not get_needs_band_plan_regulatory_update(chassis_with_band_plan)

    def test_no_band_plan_no_update_needed(self, chassis_no_band_plan):
        assert not get_needs_band_plan_regulatory_update(chassis_no_band_plan)

    def test_online_with_coverage_no_update(self, chassis_with_band_plan, frequency_band):
        assert not get_needs_band_plan_regulatory_update(chassis_with_band_plan)

    def test_online_without_coverage_needs_update(self, db, manufacturer, location):
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="Needs Update",
            model="ULXD4Q",
            ip="192.168.1.106",
            status="online",
            location=location,
            band_plan_min_mhz=900.0,
            band_plan_max_mhz=1000.0,
            band_plan_name="Non-standard",
        )
        assert get_needs_band_plan_regulatory_update(chassis)


class TestGetBandPlanRegulatoryStatus:
    def test_no_domain(self, chassis_no_location):
        chassis_no_location.band_plan_min_mhz = 470.0
        chassis_no_location.band_plan_max_mhz = 534.0
        status = get_band_plan_regulatory_status(chassis_no_location)
        assert status["has_band_plan"] is True
        assert status["has_coverage"] is False
        assert status["regulatory_domain"] is None
        msg: str = status["message"]  # type: ignore[assignment]
        assert "No regulatory domain" in msg

    def test_no_band_plan(self, chassis_no_band_plan, regulatory_domain):
        status = get_band_plan_regulatory_status(chassis_no_band_plan)
        assert status["has_band_plan"] is False
        assert status["has_coverage"] is False
        assert status["regulatory_domain"] == "FCC"
        assert status["band_plan_range"] is None
        msg: str = status["message"]  # type: ignore[assignment]
        assert "No band plan configured" in msg

    def test_full_coverage_ok(self, chassis_with_band_plan, frequency_band):
        status = get_band_plan_regulatory_status(chassis_with_band_plan)
        assert status["has_band_plan"] is True
        assert status["has_coverage"] is True
        assert status["regulatory_domain"] == "FCC"
        assert status["needs_update"] is False
        assert status["band_plan_range"] == "G50 (470-534 MHz) (470.0-534.0 MHz)"
        msg: str = status["message"]  # type: ignore[assignment]
        assert "OK" in msg

    def test_no_coverage(self, db, manufacturer, location, regulatory_domain):
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="Uncovered",
            model="ULXD4Q",
            ip="192.168.1.107",
            status="online",
            location=location,
            band_plan_min_mhz=900.0,
            band_plan_max_mhz=1000.0,
        )
        status = get_band_plan_regulatory_status(chassis)
        assert status["has_band_plan"] is True
        assert status["has_coverage"] is False
        assert status["needs_update"] is True
        msg: str = status["message"]  # type: ignore[assignment]
        assert "not covered" in msg

    def test_band_plan_range_without_name(self, db, manufacturer, location, regulatory_domain):
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            name="No Name Chassis",
            model="ULXD4Q",
            ip="192.168.1.108",
            status="online",
            location=location,
            band_plan_min_mhz=470.0,
            band_plan_max_mhz=534.0,
        )
        status = get_band_plan_regulatory_status(chassis)
        assert status["band_plan_range"] == "470.0-534.0 MHz"
