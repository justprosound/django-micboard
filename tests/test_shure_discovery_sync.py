from unittest.mock import patch

from django.test import TestCase

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.sync.discovery_orchestration_service import DiscoveryOrchestrationService
from micboard.tasks.sync.discovery import _submit_missing_ips


class FakeShureDiscoveryService:
    def __init__(self):
        """Fake discovery service used in tests to capture added IPs."""
        self.added: list[tuple[str, str, str]] = []

    def add_discovery_candidate(
        self, ip: str, manufacturer: Manufacturer, source: str = "manual"
    ) -> bool:
        self.added.append((ip, manufacturer.code, source))
        return True


class ShureDiscoverySyncTest(TestCase):
    def setUp(self) -> None:
        self.manufacturer = Manufacturer.objects.create(name="Shure", code="shure")

    def test_discovered_devices_are_persisted_from_shure_api(self):
        devices_from_api = [
            {
                "ip": "10.0.0.1",
                "type": "ulxd",
                "channels": [{"channel": 1}, {"channel": 2}],
            },
            {
                "ip": "10.0.0.2",
                "type": "qlxd",
                "channels": [],
            },
        ]

        class FakePlugin:
            def __init__(self, manufacturer):
                self.manufacturer = manufacturer

            def get_devices(self):
                return devices_from_api

        with patch(
            "micboard.manufacturers.get_manufacturer_plugin",
            return_value=FakePlugin,
        ):
            result = DiscoveryOrchestrationService.handle_discovery_requested(
                manufacturer_code="shure"
            )

        shure_result = result["shure"]
        self.assertEqual(shure_result["status"], "success")
        self.assertEqual(shure_result["count"], 2)

        persisted = DiscoveredDevice.objects.order_by("ip")
        self.assertEqual(persisted.count(), 2)
        self.assertEqual(list(persisted.values_list("ip", flat=True)), ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(persisted[0].device_type, "ulxd")
        self.assertEqual(persisted[0].channels, 2)
        self.assertEqual(persisted[1].device_type, "qlxd")
        self.assertEqual(persisted[1].channels, 0)

    def test_missing_local_ips_are_pushed_back_to_shure(self):
        DiscoveredDevice.objects.create(
            ip="10.0.0.5",
            device_type="ulxd",
            channels=1,
            manufacturer=self.manufacturer,
        )

        discovered_ips = {"10.0.0.1"}
        summary = {"missing_ips_submitted": 0, "errors": []}
        fake_service = FakeShureDiscoveryService()

        _submit_missing_ips(self.manufacturer, discovered_ips, fake_service, summary)

        self.assertEqual(fake_service.added, [("10.0.0.5", "shure", "missing_chassis")])
        self.assertEqual(summary["missing_ips_submitted"], 1)
        self.assertEqual(summary["errors"], [])
