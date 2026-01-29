import ipaddress
import logging
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


class IPConfigManager:
    """Manage IP discovery configuration for Shure System API."""

    def __init__(self):
        """Initialize IP configuration manager and connect to Shure API client."""
        config = getattr(settings, "MICBOARD_CONFIG", {})
        base_url = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
        shared_key = config.get("SHURE_API_SHARED_KEY")
        verify_ssl = config.get("SHURE_API_VERIFY_SSL", False)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ("true", "1", "yes")
        if not shared_key:
            raise ValueError(
                "SHURE_API_SHARED_KEY not configured. Set MICBOARD_SHURE_API_SHARED_KEY "
                "environment variable or update MICBOARD_CONFIG in Django settings."
            )
        self.client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
        logger.info(f"Connected to Shure System API: {base_url}")

    def validate_ip(self, ip: str) -> bool:
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    def parse_ips_from_text(self, text: str):
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ips = re.findall(ip_pattern, text)
        valid_ips = set()
        for ip in ips:
            if self.validate_ip(ip):
                valid_ips.add(ip)
        return valid_ips

    def load_ips_from_file(self, filepath: str):
        logger.info(f"Reading IPs from: {filepath}")
        try:
            with open(filepath) as f:
                text = f.read()
            ips = self.parse_ips_from_text(text)
            logger.info(f"✓ Loaded {len(ips)} unique IPs from file")
            return ips
        except FileNotFoundError:
            logger.error(f"✗ File not found: {filepath}")
            return set()

    def get_current_ips(self):
        try:
            ips = self.client.discovery.get_discovery_ips()
            return ips or []
        except Exception as e:
            logger.error(f"✗ Failed to get current IPs: {e}")
            return []

    def add_ips(self, ips, batch_size=100):
        if not ips:
            logger.warning("No IPs to add")
            return True
        ips_list = list(set(ips))
        logger.info(f"Adding {len(ips_list)} IPs in batches of {batch_size}...")
        all_success = True
        for i in range(0, len(ips_list), batch_size):
            batch = ips_list[i : i + batch_size]
            try:
                result = self.client.discovery.add_discovery_ips(batch)
                status = "✓" if result else "⚠"
                logger.info(f"{status} Batch {i // batch_size + 1}: Added {len(batch)} IPs")
            except Exception as e:
                logger.error(f"✗ Batch {i // batch_size + 1} failed: {e}")
                all_success = False
        return all_success

    def clear_ips(self):
        try:
            current = self.get_current_ips()
            if not current:
                logger.info("No IPs to clear")
                return True
            logger.info(f"Clearing {len(current)} configured IPs...")
            result = self.client.discovery.remove_discovery_ips(current)
            logger.info("✓ Cleared all IPs")
            return result
        except Exception as e:
            logger.error(f"✗ Failed to clear IPs: {e}")
            return False

    def list_ips(self):
        current = self.get_current_ips()
        if not current:
            logger.info("No discovery IPs currently configured")
            return
        logger.info(f"Currently configured discovery IPs ({len(current)} total):")
        for ip in sorted(current):
            logger.info(f"  {ip}")

    def print_summary(self):
        current = self.get_current_ips()
        logger.info("")
        logger.info("=" * 70)
        logger.info("Discovery Configuration Summary")
        logger.info("=" * 70)
        logger.info(f"Total discovery IPs: {len(current)}")
        if current:
            subnets = {}
            for ip in current:
                subnet = ".".join(ip.split(".")[:3])
                subnets[subnet] = subnets.get(subnet, 0) + 1
            logger.info("Distribution by subnet:")
            for subnet in sorted(subnets.keys()):
                logger.info(f"  {subnet}.0/24: {subnets[subnet]} IPs")


class Command(BaseCommand):
    help = "Manage Shure System API discovery IP configuration."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="List currently configured IPs")
        parser.add_argument(
            "--file", metavar="PATH", help="Load IPs from file (one per line or space-separated)"
        )
        parser.add_argument("--ips", nargs="+", metavar="IP", help="Add specific IPs")
        parser.add_argument(
            "--clear", action="store_true", help="Clear all configured IPs before adding new ones"
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            metavar="NUM",
            help="Add IPs in batches of N (default: 100)",
        )
        parser.add_argument(
            "--validate", action="store_true", help="Validate IPs before adding (slower but safer)"
        )
        parser.add_argument("--summary", action="store_true", help="Print configuration summary")

    def handle(self, *args, **options):
        try:
            manager = IPConfigManager()
            if options["list"]:
                manager.list_ips()
                return
            if options["summary"]:
                manager.print_summary()
                return
            if options["clear"]:
                if not manager.clear_ips():
                    self.stderr.write(self.style.ERROR("Failed to clear IPs."))
                    return
            ips_to_add = []
            if options["file"]:
                file_ips = manager.load_ips_from_file(options["file"])
                ips_to_add.extend(file_ips)
            if options["ips"]:
                ips_to_add.extend(options["ips"])
            if ips_to_add:
                if options["validate"]:
                    logger.info("Validating IPs...")
                    valid_ips = [ip for ip in ips_to_add if manager.validate_ip(ip)]
                    invalid_count = len(ips_to_add) - len(valid_ips)
                    if invalid_count > 0:
                        logger.warning(f"Skipping {invalid_count} invalid IPs")
                    ips_to_add = valid_ips
                if ips_to_add:
                    success = manager.add_ips(ips_to_add, batch_size=options["batch_size"])
                    manager.print_summary()
                    if not success:
                        logger.warning("Some batches may have failed. Check output above.")
                        self.stderr.write(self.style.ERROR("Some batches may have failed."))
                        return
            if (
                not options["list"]
                and not ips_to_add
                and not options["clear"]
                and not options["summary"]
            ):
                self.stdout.write(
                    self.style.WARNING("No operation specified. Use --help for options.")
                )
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            self.stderr.write(self.style.ERROR(f"Fatal error: {e}"))
            return
