from unittest.mock import Mock

from django.test import TestCase

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.sync.discovery_candidate_source_service import (
    DiscoveryCandidateSourceService,
)
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_sync_service import DiscoverySyncService


class ShureDiscoverySyncTest(TestCase):
    def setUp(self) -> None:
        self.manufacturer = Manufacturer.objects.create(name="Shure", code="shure")

    def test_missing_local_ips_are_pushed_back_to_shure(self):
        DiscoveredDevice.objects.create(
            ip="10.0.0.5",
            device_type="ulxd",
            channels=1,
            manufacturer=self.manufacturer,
        )

        summary = DiscoverySyncSummary(manufacturer=self.manufacturer.pk)
        plugin = Mock()
        plugin.add_discovery_ips.return_value = True

        DiscoverySyncService().submit_candidates(
            self.manufacturer,
            missing_ips=DiscoveryCandidateSourceService.collect_inventory_candidates(
                self.manufacturer
            ).candidates,
            scanned_ips=[],
            plugin=plugin,
            summary=summary,
        )

        plugin.add_discovery_ips.assert_called_once_with(["10.0.0.5"])
        self.assertEqual(summary.missing_ips_submitted, 1)
        self.assertEqual(summary.errors, [])
