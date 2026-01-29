import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


class DiscoveryMonitor:
    """Real-time device discovery monitor for Shure System API."""

    def __init__(self, check_interval: int = 5, summary_interval: int = 60):
        """Initialize monitor with check and summary intervals and prepare client."""
        self.check_interval = check_interval
        self.summary_interval = summary_interval
        self.last_summary = time.time()
        self.previous_devices: Dict[str, Dict[str, Any]] = {}
        self.check_count = 0
        self.start_time = datetime.now()
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
        try:
            devices = self.client.devices.get_devices()
            return {d.get("id", f"unknown-{i}"): d for i, d in enumerate(devices)}
        except Exception as e:
            logger.error(f"Error getting devices: {e}")
            return {}

    def get_discovery_ips_count(self) -> int:
        try:
            ips = self.client.discovery.get_discovery_ips()
            return len(ips) if ips else 0
        except Exception as e:
            logger.error(f"Error getting discovery IPs: {e}")
            return 0

    def format_device_info(self, device: Dict[str, Any]) -> str:
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

    def detect_changes(self, current_devices: Dict[str, Dict[str, Any]]):
        new_devices = []
        state_changes = []
        for device_id, device in current_devices.items():
            if device_id not in self.previous_devices:
                new_devices.append(device)
            else:
                old_state = self.previous_devices[device_id].get("state")
                new_state = device.get("state")
                if old_state != new_state:
                    state_changes.append((device, old_state, new_state))
        return new_devices, state_changes

    def print_summary(self, current_devices: Dict[str, Dict[str, Any]]):
        elapsed = time.time() - self.start_time.timestamp()
        elapsed_str = self._format_elapsed(elapsed)
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
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = seconds / 60
        if minutes < 60:
            return f"{minutes:.0f}m {int(seconds % 60)}s"
        hours = minutes / 60
        return f"{hours:.1f}h"

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def run(self, duration: Optional[int] = None):
        logger.info("Monitoring for new discoveries... (Ctrl+C to stop)")
        logger.info("-" * 80)
        logger.info("")
        start_time = time.time()
        try:
            while True:
                current_devices = self.get_devices()
                self.check_count += 1
                new_devices, state_changes = self.detect_changes(current_devices)
                if new_devices:
                    logger.info(
                        f"[{self._timestamp()}] 🆕 {len(new_devices)} NEW DEVICE(S) DISCOVERED:"
                    )
                    for device in new_devices:
                        logger.info(f"  ├─ {self.format_device_info(device)}")
                    logger.info("")
                if state_changes:
                    for device, _old_state, _new_state in state_changes:
                        logger.info(
                            f"[{self._timestamp()}] 🔄 STATE CHANGE: {device.get('id')} ({{old_state}} → {{new_state}})"
                        )
                    logger.info("")
                self.previous_devices = current_devices
                now = time.time()
                if now - self.last_summary >= self.summary_interval:
                    self.print_summary(current_devices)
                    logger.info("")
                    self.last_summary = now
                if duration and (now - start_time) >= duration:
                    break
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("\n" + "-" * 80)
            logger.info("Monitoring stopped by user")
            current_devices = self.get_devices()
            self.print_summary(current_devices)


class Command(BaseCommand):
    help = "Monitor Shure System API for device discoveries."

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        try:
            monitor = DiscoveryMonitor(
                check_interval=options["check_interval"],
                summary_interval=options["summary_interval"],
            )
            monitor.run(duration=options.get("duration"))
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            self.stderr.write(self.style.ERROR(f"Fatal error: {e}"))
            return
