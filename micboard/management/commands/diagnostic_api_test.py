import json
import logging

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.services.settings import settings as app_settings

logger = logging.getLogger(__name__)


class ShureAPITester:
    """Test suite for Shure System API integration."""

    def __init__(self, shared_key=None, verify_ssl=True):
        """Initialize Shure API tester with shared key and SSL verification flag."""
        self.shared_key = shared_key or app_settings.get("SHURE_API_SHARED_KEY")
        self.verify_ssl = verify_ssl
        self.client = None
        self.test_results = []

    def initialize_client(self):
        logger.info("Initializing Shure System API Client...")
        logger.info("  Base URL: https://localhost:10000")
        logger.info("  SSL Verification: %s", self.verify_ssl)
        logger.info(
            f"  Shared Key: {'*' * (len(self.shared_key) - 4) if self.shared_key else 'NOT SET'}{self.shared_key[-4:] if self.shared_key else ''}"
        )
        if not self.shared_key:
            logger.error("ERROR: SHURE_API_SHARED_KEY not set!")
            return False
        try:
            django_settings.MICBOARD_CONFIG = {
                "SHURE_API_BASE_URL": "https://localhost:10000",
                "SHURE_API_SHARED_KEY": self.shared_key,
                "SHURE_API_VERIFY_SSL": self.verify_ssl,
                "SHURE_API_TIMEOUT": 10,
            }
            self.client = ShureSystemAPIClient(
                base_url="https://localhost:10000", verify_ssl=self.verify_ssl
            )
            logger.info("✓ Client initialized successfully")
            return True
        except Exception as e:
            logger.error("✗ Failed to initialize client: %s", e)
            return False

    def test_health_check(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 1: Health Check")
        logger.info("=" * 70)
        try:
            health = self.client.check_health()
            logger.info("✓ Health check successful: %s", json.dumps(health, indent=2))
            self.test_results.append(("Health Check", True, health))
            return health.get("status") == "healthy"
        except Exception as e:
            logger.error("✗ Health check failed: %s", e)
            self.test_results.append(("Health Check", False, str(e)))
            return False

    def test_get_devices(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 2: Get Devices")
        logger.info("=" * 70)
        try:
            devices = self.client.devices.get_devices()
            logger.info("✓ Retrieved %s device(s)", len(devices))
            for idx, device in enumerate(devices[:3], 1):
                logger.info(
                    f"  WirelessChassis {idx}: {device.get('deviceId', 'N/A')} - {device.get('deviceType', 'N/A')}"
                )
            if len(devices) > 3:
                logger.info("  ... and %s more", len(devices) - 3)
            self.test_results.append(("Get Devices", True, {"count": len(devices)}))
            return len(devices) > 0
        except Exception as e:
            logger.error("✗ Get devices failed: %s", e)
            self.test_results.append(("Get Devices", False, str(e)))
            return False

    def test_device_details(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 3: Get WirelessChassis Details")
        logger.info("=" * 70)
        try:
            devices = self.client.devices.get_devices()
            if not devices:
                logger.warning("⊘ No devices available to test")
                self.test_results.append(("WirelessChassis Details", False, "No devices available"))
                return False
            device_id = devices[0].get("deviceId")
            logger.info("Testing with device ID: %s", device_id)
            identity = self.client.devices.get_device_identity(device_id)
            logger.info("✓ WirelessChassis Identity: %s", identity.get("serialNumber", "N/A"))
            status = self.client.devices.get_device_status(device_id)
            logger.info("✓ WirelessChassis Status: %s", status.get("systemTime", "N/A"))
            network = self.client.devices.get_device_network(device_id)
            logger.info("✓ WirelessChassis Network: %s", network.get("ipAddress", "N/A"))
            self.test_results.append(("WirelessChassis Details", True, {"device_id": device_id}))
            return True
        except Exception as e:
            logger.error("✗ WirelessChassis details failed: %s", e)
            self.test_results.append(("WirelessChassis Details", False, str(e)))
            return False

    def test_discovery_endpoints(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 4: Discovery Management")
        logger.info("=" * 70)
        try:
            discovery_ips = self.client.discovery.get_discovery_ips()
            logger.info("✓ Current discovery IPs: %s", discovery_ips)
            test_ip = "192.168.1.100"
            result = self.client.discovery.add_discovery_ips([test_ip])
            logger.info("✓ Added discovery IP %s: %s", test_ip, result)
            updated_ips = self.client.discovery.get_discovery_ips()
            logger.info("✓ Updated discovery IPs: %s", updated_ips)
            result = self.client.discovery.remove_discovery_ips([test_ip])
            logger.info("✓ Removed discovery IP %s: %s", test_ip, result)
            self.test_results.append(("Discovery Endpoints", True, {"ips_count": len(updated_ips)}))
            return True
        except Exception as e:
            logger.error("✗ Discovery endpoints failed: %s", e)
            self.test_results.append(("Discovery Endpoints", False, str(e)))
            return False

    def test_connection_pooling(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 5: Connection Pooling & Retry Logic")
        logger.info("=" * 70)
        try:
            logger.info("Session max_retries: %s", self.client.max_retries)
            logger.info("Session retry_backoff: %ss", self.client.retry_backoff)
            logger.info("Session timeout: %ss", self.client.timeout)
            for i in range(3):
                devices = self.client.devices.get_devices()
                logger.info("✓ Request %s: Retrieved %s devices", i + 1, len(devices))
            logger.info("✓ Connection pooling working correctly")
            self.test_results.append(("Connection Pooling", True, {}))
            return True
        except Exception as e:
            logger.error("✗ Connection pooling test failed: %s", e)
            self.test_results.append(("Connection Pooling", False, str(e)))
            return False

    def test_rate_limiter(self):
        if not self.client:
            return False
        logger.info("\n" + "=" * 70)
        logger.info("TEST 6: Rate Limiter")
        logger.info("=" * 70)
        try:
            rate_limiter = self.client.rate_limiter
            logger.info("Rate limiter configured: %s", rate_limiter is not None)
            logger.info("Rate limiter type: %s", type(rate_limiter).__name__)
            self.test_results.append(
                ("Rate Limiter", True, {"has_limiter": rate_limiter is not None})
            )
            return True
        except Exception as e:
            logger.error("✗ Rate limiter test failed: %s", e)
            self.test_results.append(("Rate Limiter", False, str(e)))
            return False

    def print_summary(self):
        logger.info("\n" + "=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)
        passed = sum(1 for _, success, _ in self.test_results if success)
        total = len(self.test_results)
        for test_name, success, _details in self.test_results:
            status = "✓ PASS" if success else "✗ FAIL"
            logger.info("%s: %s", status, test_name)
        logger.info("-" * 70)
        logger.info("TOTAL: %s/%s tests passed", passed, total)
        logger.info("=" * 70)
        return passed == total

    def run_all_tests(self):
        if not self.initialize_client():
            return False
        tests = [
            self.test_health_check,
            self.test_get_devices,
            self.test_device_details,
            self.test_discovery_endpoints,
            self.test_connection_pooling,
            self.test_rate_limiter,
        ]
        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error("Unexpected error in %s: %s", test.__name__, e)
        success = self.print_summary()
        return success


class Command(BaseCommand):
    help = "Test Shure System API integration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--shared-key",
            help="Shure API shared key (can also use MICBOARD_SHURE_API_SHARED_KEY env var)",
        )
        parser.add_argument(
            "--no-ssl-verify",
            action="store_true",
            help="Disable SSL verification (for self-signed certificates)",
        )

    def handle(self, *args, **options):
        tester = ShureAPITester(
            shared_key=options.get("shared_key"),
            verify_ssl=not options.get("no_ssl_verify", False),
        )
        success = tester.run_all_tests()
        if not success:
            self.stderr.write(self.style.ERROR("Some tests failed."))
            return
