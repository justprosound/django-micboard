#!/usr/bin/env python
"""Shure System API: Real-Time WirelessChassis Discovery Monitor.

Continuously monitors Shure System API for new device discoveries and state changes.
Alerts in real-time when devices appear, go ONLINE, or change state.

Usage:
    python scripts/shure_discovery_monitor.py [--check-interval SECONDS] [--summary-interval SECONDS]

Environment Variables:
    MICBOARD_SHURE_API_BASE_URL      - API base URL (default: https://localhost:10000)
    MICBOARD_SHURE_API_SHARED_KEY    - API shared key (REQUIRED)
    MICBOARD_SHURE_API_VERIFY_SSL    - Verify SSL certificates (default: false)

Examples:
    # Monitor with 5-second check interval
    python scripts/shure_discovery_monitor.py --check-interval 5

    # Monitor with custom summary interval (every 30 seconds)
    python scripts/shure_discovery_monitor.py --summary-interval 30

Troubleshooting:
    - If no devices appear: See docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md
    - If connection refused: Check API is running on https://localhost:10000
    - If authentication fails: Verify MICBOARD_SHURE_API_SHARED_KEY environment variable

NOTE: If you see 0 devices after configuring IPs, the most common cause is an
incorrect NetworkInterfaceId GUID in the Shure System API config. See the
troubleshooting guide for diagnosis and fix.
"""

import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional

# Setup Django first
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()

from django.conf import settings

from micboard.integrations.shure.client import ShureSystemAPIClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class DiscoveryMonitor:
    """Real-time device discovery monitor for Shure System API."""

    def __init__(self, check_interval: int = 5, summary_interval: int = 60):
        """Initialize the discovery monitor.

        Args:
            check_interval: How often to check for device changes (seconds)
            summary_interval: How often to print summary (seconds)
        """
        self.check_interval = check_interval
        self.summary_interval = summary_interval
        self.last_summary = time.time()

        # Track state
        self.previous_devices: Dict[str, Dict[str, Any]] = {}
        self.check_count = 0
        self.start_time = datetime.now()

        # Initialize client
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

        logger.info("=" * 80)
        logger.info("Shure System API - WirelessChassis Discovery Monitor")
        logger.info("=" * 80)
        logger.info(f"API: {base_url}")
        logger.info(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        try:
            self.client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
            logger.info("✓ Connected to Shure System API")
        except Exception as e:
            logger.error(f"✗ Failed to initialize API client: {e}")
            raise

    def get_devices(self) -> Dict[str, Dict[str, Any]]:
        """Fetch current devices from API, keyed by device ID."""
        try:
            devices = self.client.devices.get_devices()
            return {d.get("id", f"unknown-{i}"): d for i, d in enumerate(devices)}
        except Exception as e:
            logger.error(f"Error getting devices: {e}")
            return {}

    def get_discovery_ips_count(self) -> int:
        """Get count of configured discovery IPs."""
        try:
            ips = self.client.discovery.get_discovery_ips()
            return len(ips) if ips else 0
        except Exception as e:
            logger.error(f"Error getting discovery IPs: {e}")
            return 0

    def format_device_info(self, device: Dict[str, Any]) -> str:
        """Format device info for display."""
        model = device.get("model", "Unknown")
        ip = device.get("id", "Unknown")
        state = device.get("state", "Unknown")
        fw = (
            device.get("properties", {}).get("firmware_version", "Unknown")
            if isinstance(device.get("properties"), dict)
            else "Unknown"
        )
        serial = (
            device.get("properties", {}).get("serial_number", "")
            if isinstance(device.get("properties"), dict)
            else ""
        )

        info = f"{model:<20} @ {ip:<18} State: {state:<12} Firmware: {fw:<15}"
        if serial:
            info += f" Serial: {serial}"
        return info

    def detect_changes(self, current_devices: Dict[str, Dict[str, Any]]) -> tuple:
        """Detect new devices and state changes.

        Returns:
            (new_devices, state_changes) - lists of device info
        """
        new_devices = []
        state_changes = []

        # Check for new devices
        for device_id, device in current_devices.items():
            if device_id not in self.previous_devices:
                new_devices.append(device)
            else:
                # Check for state changes
                old_state = self.previous_devices[device_id].get("state")
                new_state = device.get("state")
                if old_state != new_state:
                    state_changes.append((device, old_state, new_state))

        return new_devices, state_changes

    def print_summary(self, current_devices: Dict[str, Dict[str, Any]]):
        """Print periodic summary of discovery status."""
        elapsed = time.time() - self.start_time.timestamp()
        elapsed_str = self._format_elapsed(elapsed)

        # Count by state
        state_counts = defaultdict(int)
        for device in current_devices.values():
            state = device.get("state", "UNKNOWN")
            state_counts[state] += 1

        state_str = ", ".join([f"{state}:{count}" for state, count in sorted(state_counts.items())])
        if not state_str:
            state_str = "NONE"

        discovery_ips = self.get_discovery_ips_count()

        logger.info(f"[{self._timestamp()}] 📊 SUMMARY (after {elapsed_str}):")
        logger.info(f"  Total devices: {len(current_devices)} ({state_str})")
        logger.info(f"  Discovery IPs: {discovery_ips} configured")
        logger.info(f"  Checks: {self.check_count}")

    def _format_elapsed(self, seconds: float) -> str:
        """Format elapsed seconds as human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.0f}m {int(seconds % 60)}s"
        hours = minutes / 60
        return f"{hours:.1f}h"

    def _timestamp(self) -> str:
        """Get current time as HH:MM:SS."""
        return datetime.now().strftime("%H:%M:%S")

    def run(self, duration: Optional[int] = None):
        """Run the monitor loop.

        Args:
            duration: How long to run in seconds (None = infinite)
        """
        logger.info("Monitoring for new discoveries... (Ctrl+C to stop)")
        logger.info("-" * 80)
        logger.info("")

        start_time = time.time()

        try:
            while True:
                # Get current devices
                current_devices = self.get_devices()
                self.check_count += 1

                # Detect changes
                new_devices, state_changes = self.detect_changes(current_devices)

                # Alert on new devices
                if new_devices:
                    logger.info(
                        f"[{self._timestamp()}] 🆕 {len(new_devices)} NEW DEVICE(S) DISCOVERED:"
                    )
                    for device in new_devices:
                        logger.info(f"  ├─ {self.format_device_info(device)}")
                    logger.info("")

                # Alert on state changes
                if state_changes:
                    for device, old_state, new_state in state_changes:
                        logger.info(
                            f"[{self._timestamp()}] 🔄 STATE CHANGE: {device.get('id')} "
                            f"({old_state} → {new_state})"
                        )
                    logger.info("")

                # Update previous state
                self.previous_devices = current_devices

                # Print periodic summary
                now = time.time()
                if now - self.last_summary >= self.summary_interval:
                    self.print_summary(current_devices)
                    logger.info("")
                    self.last_summary = now

                # Check duration
                if duration and (now - start_time) >= duration:
                    break

                # Wait before next check
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("\n" + "-" * 80)
            logger.info("Monitoring stopped by user")
            # Print final summary
            current_devices = self.get_devices()
            self.print_summary(current_devices)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor Shure System API for device discoveries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Troubleshooting:
  - If no devices appear: Check NetworkInterfaceId GUID in Shure API config
    See: docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md
  - If connection refused: Ensure Shure System API is running
  - If authentication fails: Check MICBOARD_SHURE_API_SHARED_KEY env var
        """,
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=5,
        metavar="SECONDS",
        help="How often to check for changes (default: 5 seconds)",
    )
    parser.add_argument(
        "--summary-interval",
        type=int,
        default=60,
        metavar="SECONDS",
        help="How often to print summary (default: 60 seconds)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        metavar="SECONDS",
        help="Run for specified seconds (default: infinite)",
    )

    args = parser.parse_args()

    try:
        monitor = DiscoveryMonitor(
            check_interval=args.check_interval, summary_interval=args.summary_interval
        )
        monitor.run(duration=args.duration)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
