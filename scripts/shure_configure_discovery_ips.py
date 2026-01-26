#!/usr/bin/env python
r"""Shure System API: Bulk IP Discovery Configuration.

Add or manage IP addresses for device discovery in Shure System API.
Supports adding from file, CLI arguments, or discovering via subnet scanning.

Usage:
    # Add IPs from file (one per line or space-separated)
    python scripts/shure_configure_discovery_ips.py --file ips.txt

    # Add specific IPs
    python scripts/shure_configure_discovery_ips.py --ips 172.21.0.1 172.21.1.1 172.21.2.1

    # Get current configured IPs
    python scripts/shure_configure_discovery_ips.py --list

    # Clear all IPs (then add new ones)
    python scripts/shure_configure_discovery_ips.py --clear --file ips.txt

    # Add with batch size (useful for large IP counts)
    python scripts/shure_configure_discovery_ips.py --file ips.txt --batch-size 50

Environment Variables:
    MICBOARD_SHURE_API_BASE_URL      - API base URL (default: https://localhost:10000)
    MICBOARD_SHURE_API_SHARED_KEY    - API shared key (REQUIRED)
    MICBOARD_SHURE_API_VERIFY_SSL    - Verify SSL certificates (default: false)

Examples:
    # Add 172.21.x.x subnets (319 IPs)
    python scripts/shure_configure_discovery_ips.py \\
        --ips $(seq -f "172.21.%g.1" 0 255)

    # Load from file with validation
    python scripts/shure_configure_discovery_ips.py --file campus_ips.txt --validate

Troubleshooting:
    - If IPs don't get added: Check MICBOARD_SHURE_API_SHARED_KEY
    - If "202 Accepted" but nothing happens: See SHURE_NETWORK_GUID_TROUBLESHOOTING.md
    - If API connection fails: Ensure Shure System API is running and accessible
"""

import argparse
import ipaddress
import logging
import os
import re
import sys
from typing import List, Set

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()

from django.conf import settings

from micboard.integrations.shure.client import ShureSystemAPIClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class IPConfigManager:
    """Manage IP discovery configuration for Shure System API."""

    def __init__(self):
        """Initialize the manager."""
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
        """Validate IP address format."""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    def parse_ips_from_text(self, text: str) -> Set[str]:
        """Parse IPs from free-form text (space or newline separated)."""
        # IP pattern
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ips = re.findall(ip_pattern, text)

        # Validate each
        valid_ips = set()
        for ip in ips:
            if self.validate_ip(ip):
                valid_ips.add(ip)

        return valid_ips

    def load_ips_from_file(self, filepath: str) -> Set[str]:
        """Load IPs from file (one per line or space-separated)."""
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

    def get_current_ips(self) -> List[str]:
        """Get currently configured discovery IPs."""
        try:
            ips = self.client.discovery.get_discovery_ips()
            return ips or []
        except Exception as e:
            logger.error(f"✗ Failed to get current IPs: {e}")
            return []

    def add_ips(self, ips: List[str], batch_size: int = 100) -> bool:
        """Add IPs to discovery configuration.

        Args:
            ips: List of IP addresses
            batch_size: How many IPs to add per request

        Returns:
            True if all batches succeeded
        """
        if not ips:
            logger.warning("No IPs to add")
            return True

        ips_list = list(set(ips))  # Deduplicate
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

    def clear_ips(self) -> bool:
        """Remove all configured IPs."""
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
        """List currently configured IPs."""
        current = self.get_current_ips()

        if not current:
            logger.info("No discovery IPs currently configured")
            return

        logger.info(f"Currently configured discovery IPs ({len(current)} total):")
        for ip in sorted(current):
            logger.info(f"  {ip}")

    def print_summary(self):
        """Print current discovery configuration summary."""
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage Shure System API discovery IP configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List current IPs
  python scripts/shure_configure_discovery_ips.py --list

  # Add from file
  python scripts/shure_configure_discovery_ips.py --file campus_ips.txt

  # Add specific IPs
  python scripts/shure_configure_discovery_ips.py --ips 172.21.0.1 172.21.1.1

  # Clear and reload
  python scripts/shure_configure_discovery_ips.py --clear --file ips.txt
        """,
    )

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

    args = parser.parse_args()

    try:
        manager = IPConfigManager()

        # List operation
        if args.list:
            manager.list_ips()
            return

        # Summary operation
        if args.summary:
            manager.print_summary()
            return

        # Clear operation
        if args.clear:
            if not manager.clear_ips():
                sys.exit(1)

        # Collect IPs to add
        ips_to_add = []

        if args.file:
            file_ips = manager.load_ips_from_file(args.file)
            ips_to_add.extend(file_ips)

        if args.ips:
            ips_to_add.extend(args.ips)

        # Add IPs
        if ips_to_add:
            if args.validate:
                logger.info("Validating IPs...")
                valid_ips = [ip for ip in ips_to_add if manager.validate_ip(ip)]
                invalid_count = len(ips_to_add) - len(valid_ips)
                if invalid_count > 0:
                    logger.warning(f"Skipping {invalid_count} invalid IPs")
                ips_to_add = valid_ips

            if ips_to_add:
                success = manager.add_ips(ips_to_add, batch_size=args.batch_size)
                manager.print_summary()

                if not success:
                    logger.warning("Some batches may have failed. Check output above.")
                    sys.exit(1)

        if not args.list and not ips_to_add and not args.clear and not args.summary:
            parser.print_help()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
