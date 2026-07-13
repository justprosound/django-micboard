import logging

from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.services.settings import settings

logger = logging.getLogger(__name__)


class HealthChecker:
    """Perform health checks on Shure System API."""

    def __init__(self):
        """Initialize health checker and configure Shure System API client."""
        base_url = settings.get("SHURE_API_BASE_URL", "https://localhost:10000")
        shared_key = settings.get("SHURE_API_SHARED_KEY")
        verify_ssl = settings.get("SHURE_API_VERIFY_SSL", False)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ("true", "1", "yes")
        if not shared_key:
            raise ValueError(
                "SHURE_API_SHARED_KEY not configured. Set MICBOARD_SHURE_API_SHARED_KEY "
                "environment variable or update MICBOARD_CONFIG in Django settings."
            )
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.client: ShureSystemAPIClient | None = None
        self.error = ""
        try:
            self.client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
        except Exception as e:
            self.client = None
            self.error = str(e)

    def check_connectivity(self):
        logger.info("1. Connectivity Check\n" + "-" * 70)
        if not self.client:
            logger.error("✗ Failed to initialize client: %s", self.error)
            return {"status": "failed", "error": self.error}
        try:
            health = self.client.check_health()
            is_healthy = health.get("status") == "healthy"
            status_icon = "✓" if is_healthy else "⚠"
            logger.info("%s Base URL: %s", status_icon, self.base_url)
            logger.info("%s Status: %s", status_icon, health.get("status"))
            logger.info("%s Response Code: %s", status_icon, health.get("status_code"))
            if health.get("error"):
                logger.error("  Error: %s", health["error"])
            return health
        except Exception as e:
            logger.error("✗ Connectivity check failed: %s", e)
            return {"status": "failed", "error": str(e)}

    def check_devices(self):
        logger.info("\n2. WirelessChassis Discovery Check\n" + "-" * 70)
        if not self.client:
            logger.error("✗ Client not initialized")
            return {}
        try:
            devices = self.client.devices.get_devices()
            count = len(devices)
            if count == 0:
                logger.warning("⚠ No devices discovered (0/539 configured IPs)")
                logger.info("  This is usually caused by incorrect NetworkInterfaceId GUID")
                logger.info("  See: docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md")
            else:
                logger.info("✓ Found %s device(s)", count)
                states: dict[str, int] = {}
                for device in devices:
                    state = device.get("state", "UNKNOWN")
                    states[state] = states.get(state, 0) + 1
                for state, count in sorted(states.items()):
                    logger.info("  %s: %s", state, count)
            return {"device_count": len(devices), "devices": devices}
        except Exception as e:
            logger.error("✗ WirelessChassis check failed: %s", e)
            return {}

    def check_discovery_ips(self):
        logger.info("\n3. Discovery IP Configuration Check\n" + "-" * 70)
        if not self.client:
            logger.error("✗ Client not initialized")
            return {}
        try:
            ips = self.client.discovery.get_discovery_ips()
            if not ips:
                logger.warning("⚠ No discovery IPs configured")
            else:
                logger.info("✓ Configured IPs: %s", len(ips))
                subnets: dict[str, int] = {}
                for ip in ips:
                    subnet = ".".join(ip.split(".")[:3])
                    subnets[subnet] = subnets.get(subnet, 0) + 1
                logger.info("  Distribution by subnet:")
                for subnet in sorted(subnets.keys()):
                    logger.info("    %s.0/24: %s IPs", subnet, subnets[subnet])
            return {"ip_count": len(ips), "ips": ips}
        except Exception as e:
            logger.error("✗ Discovery IP check failed: %s", e)
            return {}

    def check_api_endpoints(self):
        logger.info("\n4. API Endpoints Check\n" + "-" * 70)
        if not self.client:
            logger.error("✗ Client not initialized")
            return {}
        endpoints = {
            "/api/v1/devices": "WirelessChassis listing",
            "/api/v1/config/discovery/ips": "IP discovery configuration",
        }
        results: dict[str, int | str] = {}
        for endpoint, description in endpoints.items():
            try:
                response = self.client.client.get(f"{self.base_url}{endpoint}", timeout=5)
                status = "✓" if response.status_code == 200 else "⚠"
                logger.info("%s %-40s %s - %s", status, endpoint, response.status_code, description)
                results[endpoint] = response.status_code
            except Exception as e:
                logger.error("✗ %-40s ERROR - %s", endpoint, description)
                logger.error("  %s", e)
                results[endpoint] = f"ERROR: {e}"
        return results

    def check_client_config(self):
        logger.info("\n5. Client Configuration\n" + "-" * 70)
        if not self.client:
            logger.error("✗ Client not initialized")
            return {}
        logger.info("✓ Base URL: %s", self.client.base_url)
        logger.info("✓ Timeout: %ss", self.client.timeout)
        logger.info("✓ Max Retries: %s", self.client.max_retries)
        logger.info("✓ Retry Backoff: %ss", self.client.retry_backoff)
        logger.info("✓ SSL Verification: %s", self.client.verify_ssl)
        logger.info("✓ Health Status: %s", "Healthy" if self.client.is_healthy() else "Degraded")
        return {
            "base_url": self.client.base_url,
            "timeout": self.client.timeout,
            "max_retries": self.client.max_retries,
            "is_healthy": self.client.is_healthy(),
        }

    def print_summary(self, full: bool = False):
        logger.info("\n" + "=" * 70)
        logger.info("HEALTH CHECK SUMMARY")
        logger.info("=" * 70)
        connectivity = self.check_connectivity()
        devices = self.check_devices()
        ips = self.check_discovery_ips()
        self.check_api_endpoints()
        self.check_client_config()
        logger.info("\n" + "=" * 70)
        all_good = (
            connectivity.get("status") == "healthy"
            and devices.get("device_count", 0) > 0
            and ips.get("ip_count", 0) > 0
        )
        if all_good:
            logger.info("✓ ALL SYSTEMS OPERATIONAL")
        else:
            logger.info("⚠ ISSUES DETECTED - See above for details")
        logger.info("=" * 70)
        if connectivity.get("status") != "healthy":
            logger.info("\n📋 Recommendations:")
            logger.info("  • Check if Shure System API service is running")
            logger.info("  • Verify base URL: https://localhost:10000")
            logger.info("  • Check firewall rules for port 10000")
        if devices.get("device_count", 0) == 0 and ips.get("ip_count", 0) > 0:
            logger.info("\n📋 Recommendations:")
            logger.info("  • Check NetworkInterfaceId GUID in Shure API config")
            logger.info("  • See: docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md")
            logger.info("  • Verify firewall allows UDP 8427 (SLP)")
        if ips.get("ip_count", 0) == 0:
            logger.info("\n📋 Recommendations:")
            logger.info("  • Configure discovery IPs:")
            logger.info("  • python scripts/shure_configure_discovery_ips.py --help")

    def run(self, full: bool = False):
        self.print_summary(full=full)


class Command(BaseCommand):
    help = "Perform health checks on Shure System API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full", action="store_true", help="Run full diagnostics including device details"
        )

    def handle(self, *args, **options):
        try:
            checker = HealthChecker()
            checker.run(full=options["full"])
        except Exception as e:
            logger.error("Fatal error: %s", e)
            self.stderr.write(self.style.ERROR(f"Fatal error: {e}"))
            return
