"""Tests for tenant filtering helpers."""

from __future__ import annotations

from django.contrib.sites.models import Site
from django.test import TestCase, override_settings

from micboard.models.locations.structure import Building, Location, Room
from micboard.services.tenant_filters import apply_tenant_filters


class TenantFilterHelperTests(TestCase):
    """Validate apply_tenant_filters behavior in multi-site mode."""

    @override_settings(MICBOARD_MULTI_SITE_MODE=True)
    def test_apply_tenant_filters_by_site(self) -> None:
        """Filter locations by site when multi-site mode is enabled."""
        site_one = Site.objects.create(name="Site One", domain="site-one.test")
        site_two = Site.objects.create(name="Site Two", domain="site-two.test")

        building_one = Building.objects.create(name="Building One", site=site_one)
        building_two = Building.objects.create(name="Building Two", site=site_two)

        room_one = Room.objects.create(building=building_one, name="Room A")
        room_two = Room.objects.create(building=building_two, name="Room B")

        location_one = Location.objects.create(
            name="Location A",
            building=building_one,
            room=room_one,
        )
        Location.objects.create(
            name="Location B",
            building=building_two,
            room=room_two,
        )

        filtered = apply_tenant_filters(
            Location.objects.all(),
            site_id=site_one.id,
            building_path="building",
        )

        self.assertEqual(list(filtered), [location_one])
