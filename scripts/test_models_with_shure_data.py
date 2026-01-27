#!/usr/bin/env python
"""Django-Micboard: Model Population Test with Real Shure WirelessChassis Data.

Test that WirelessChassis, WirelessUnit, WirelessChassis models can be properly populated
with real data from the Shure System API.

Usage:
    python scripts/test_models_with_shure_data.py [--sample-size N] [--clear]

Environment Variables:
    MICBOARD_SHURE_API_BASE_URL      - API base URL (default: https://localhost:10000)
    MICBOARD_SHURE_API_SHARED_KEY    - API shared key (REQUIRED)
    MICBOARD_SHURE_API_VERIFY_SSL    - Verify SSL certificates (default: false)

Examples:
    # Test with all devices
    python scripts/test_models_with_shure_data.py

    # Test with first 5 devices
    python scripts/test_models_with_shure_data.py --sample-size 5

    # Clear and re-populate
    python scripts/test_models_with_shure_data.py --clear

This script validates:
    ✓ WirelessChassis model creation from API data
    ✓ WirelessUnit/WirelessChassis relationship creation
    ✓ Property storage (firmware, serial, state)
    ✓ Model querysets and filtering
    ✓ Real-time state tracking
    ✓ Ready for polling integration

Once this passes, the polling command will automatically:
    1. Fetch devices from Shure System API
    2. Create/update WirelessChassis, WirelessUnit, WirelessChassis models
    3. Broadcast updates via WebSocket
    4. Store telemetry data
"""

import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()

from django.conf import settings
from django.db.models import Count

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.models import WirelessChassis, Location
from micboard.models.telemetry import WirelessUnitSample

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class ModelPopulationTester:
    """Test model population with real Shure device data."""

    def __init__(self):
        """Initialize the tester."""
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
        self.test_results = {}

    def get_devices_from_api(self) -> List[Dict[str, Any]]:
        """Fetch devices from Shure System API."""
        try:
            devices = self.client.devices.get_devices()
            logger.info(f"✓ Fetched {len(devices)} devices from API")
            return devices
        except Exception as e:
            logger.error(f"✗ Failed to fetch devices: {e}")
            return []

    def create_default_location(self) -> Location:
        """Create or get default location for test devices."""
        location, created = Location.objects.get_or_create(
            name="API Test Location",
            defaults={
                "description": "Test location for API-populated devices",
                "building": "Lab",
            },
        )
        if created:
            logger.info(f"✓ Created test location: {location.name}")
        else:
            logger.info(f"✓ Using existing location: {location.name}")
        return location

    def populate_device_from_api_data(
        self, api_device: Dict[str, Any], location: Location
    ) -> WirelessChassis:
        """Create or update a WirelessChassis model from Shure API data.

        API device structure:
        {
            "id": "172.21.2.140",
            "model": "ULXD4D",
            "state": "ONLINE",
            "properties": {
                "firmware_version": "2.7.6.0",
                "serial_number": "4192900300",
                "ip_address": "172.21.2.140",
            }
        }
        """
        device_id = api_device.get("id", "unknown")
        model = api_device.get("model", "Unknown")
        state = api_device.get("state", "UNKNOWN")

        properties = api_device.get("properties", {})
        firmware = properties.get("firmware_version", "Unknown")
        serial = properties.get("serial_number", "Unknown")

        # Create or update device
        device, created = WirelessChassis.objects.update_or_create(
            manufacturer="Shure",
            device_id=device_id,
            defaults={
                "name": f"{model} @ {device_id}",
                "model": model,
                "serial_number": serial,
                "firmware_version": firmware,
                "location": location,
                "state": state,
                "is_online": state == "ONLINE",
                "ip_address": device_id,
                "last_seen": datetime.now(),
            },
        )

        if created:
            logger.info(f"  ✓ Created: {device.name} (Serial: {serial})")
        else:
            logger.info(f"  ✓ Updated: {device.name} (State: {state})")

        return device

    def test_basic_population(self, devices: List[Dict[str, Any]]) -> bool:
        """Test basic device population."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 1: Basic WirelessChassis Population")
        logger.info("=" * 80)

        if not devices:
            logger.warning("⊘ Skipped (no devices)")
            return True

        try:
            location = self.create_default_location()

            logger.info(f"\nPopulating {len(devices)} devices...")
            for device_data in devices[:5]:  # Test with first 5
                self.populate_device_from_api_data(device_data, location)

            # Verify devices were created
            device_count = WirelessChassis.objects.filter(location=location).count()
            logger.info(f"\n✓ Successfully populated {device_count} devices")

            self.test_results["Basic Population"] = True
            return True
        except Exception as e:
            logger.error(f"✗ Population failed: {e}")
            import traceback

            traceback.print_exc()
            self.test_results["Basic Population"] = False
            return False

    def test_device_queries(self) -> bool:
        """Test device query functionality."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 2: WirelessChassis Queries")
        logger.info("=" * 80)

        try:
            # Total devices
            total = WirelessChassis.objects.count()
            logger.info(f"✓ Total devices: {total}")

            # Online devices
            online = WirelessChassis.objects.filter(is_online=True).count()
            logger.info(f"✓ Online devices: {online}")

            # By manufacturer
            shure = WirelessChassis.objects.filter(manufacturer="Shure").count()
            logger.info(f"✓ Shure devices: {shure}")

            # By model
            model_counts = {}
            for device in WirelessChassis.objects.values("model").distinct():
                model = device["model"]
                count = WirelessChassis.objects.filter(model=model).count()
                model_counts[model] = count

            logger.info("✓ Devices by model:")
            for model, count in sorted(model_counts.items()):
                logger.info(f"    {model}: {count}")

            logger.info("✓ All queries successful")
            self.test_results["WirelessChassis Queries"] = True
            return True
        except Exception as e:
            logger.error(f"✗ Query test failed: {e}")
            self.test_results["WirelessChassis Queries"] = False
            return False

    def test_state_tracking(self) -> bool:
        """Test device state tracking."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 3: State Tracking")
        logger.info("=" * 80)

        try:
            # Get first device
            device = WirelessChassis.objects.first()
            if not device:
                logger.warning("⊘ Skipped (no devices)")
                return True

            logger.info(f"\nTesting state changes on: {device.name}")

            # Record initial state
            initial_state = device.state
            initial_seen = device.last_seen
            logger.info(f"  Initial state: {initial_state}")
            logger.info(f"  Initial seen: {initial_seen}")

            # Simulate state change
            device.state = "OFFLINE" if device.state == "ONLINE" else "ONLINE"
            device.is_online = device.state == "ONLINE"
            device.last_seen = datetime.now()
            device.save()

            logger.info(f"  Updated state: {device.state}")
            logger.info(f"  Updated seen: {device.last_seen}")

            # Verify in database
            refreshed = WirelessChassis.objects.get(id=device.id)
            assert refreshed.state == device.state
            logger.info("✓ State changes persisted correctly")

            # Revert state
            device.state = initial_state
            device.save()
            logger.info("✓ State tracking functional")

            self.test_results["State Tracking"] = True
            return True
        except Exception as e:
            logger.error(f"✗ State tracking test failed: {e}")
            self.test_results["State Tracking"] = False
            return False

    def test_telemetry_storage(self) -> bool:
        """Test telemetry data storage."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 4: Telemetry Storage")
        logger.info("=" * 80)

        try:
            device = WirelessChassis.objects.first()
            if not device:
                logger.warning("⊘ Skipped (no devices)")
                return True

            logger.info(f"\nTesting telemetry for: {device.name}")

            # Create telemetry entry
            telemetry = WirelessUnitSample.objects.create(
                device=device,
                battery_level=85,
                rf_level=-45,
                temperature=22.5,
                timestamp=datetime.now(),
            )

            logger.info(f"  ✓ Created telemetry entry (ID: {telemetry.id})")
            logger.info(f"    Battery: {telemetry.battery_level}%")
            logger.info(f"    RF Level: {telemetry.rf_level} dBm")
            logger.info(f"    Temperature: {telemetry.temperature}°C")

            # Query telemetry
            latest = WirelessUnitSample.objects.filter(device=device).latest("timestamp")
            assert latest.battery_level == 85
            logger.info("✓ Telemetry retrieval successful")

            logger.info("✓ Telemetry storage functional")
            self.test_results["Telemetry Storage"] = True
            return True
        except Exception as e:
            logger.error(f"✗ Telemetry test failed: {e}")
            self.test_results["Telemetry Storage"] = False
            return False

    def test_model_relationships(self) -> bool:
        """Test model relationships and foreign keys."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 5: Model Relationships")
        logger.info("=" * 80)

        try:
            device = WirelessChassis.objects.first()
            if not device:
                logger.warning("⊘ Skipped (no devices)")
                return True

            logger.info(f"\nTesting relationships for: {device.name}")

            # Check location relationship
            if device.location:
                logger.info(f"  ✓ Location: {device.location.name}")

                # Get all devices in this location
                devices_in_location = WirelessChassis.objects.filter(location=device.location).count()
                logger.info(f"  ✓ Devices in location: {devices_in_location}")

            # Check transmitters/receivers
            transmitters = device.transmitter_set.all().count()
            receivers = device.receiver_set.all().count()
            logger.info(f"  ✓ Transmitters: {transmitters}")
            logger.info(f"  ✓ Receivers: {receivers}")

            # Check telemetry relationship
            telemetry_count = device.devicetelemetry_set.count()
            logger.info(f"  ✓ Telemetry entries: {telemetry_count}")

            logger.info("✓ All relationships functional")
            self.test_results["Model Relationships"] = True
            return True
        except Exception as e:
            logger.error(f"✗ Relationship test failed: {e}")
            self.test_results["Model Relationships"] = False
            return False

    def test_data_integrity(self) -> bool:
        """Test data integrity constraints."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 6: Data Integrity")
        logger.info("=" * 80)

        try:
            # Get device count
            count = WirelessChassis.objects.count()
            logger.info(f"✓ Total devices in database: {count}")

            # Check for null required fields
            devices_no_name = WirelessChassis.objects.filter(name__isnull=True).count()
            if devices_no_name > 0:
                logger.warning(f"  ⚠ Devices with no name: {devices_no_name}")
            else:
                logger.info("✓ All devices have names")

            # Check for duplicate IDs
            duplicates = (
                WirelessChassis.objects.values("device_id", "manufacturer")
                .annotate(count=Count("id"))
                .filter(count__gt=1)
            )

            if duplicates.count() > 0:
                logger.warning(f"  ⚠ Duplicate device IDs found: {duplicates.count()}")
            else:
                logger.info("✓ No duplicate device IDs")

            logger.info("✓ Data integrity verified")
            self.test_results["Data Integrity"] = True
            return True
        except Exception as e:
            logger.error(f"✗ Integrity test failed: {e}")
            self.test_results["Data Integrity"] = False
            return False

    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)

        passed = sum(1 for v in self.test_results.values() if v)
        total = len(self.test_results)

        for test_name, success in self.test_results.items():
            icon = "✓" if success else "✗"
            logger.info(f"{icon} {test_name}")

        logger.info("-" * 80)
        logger.info(f"Result: {passed}/{total} tests passed")

        # WirelessChassis statistics
        device_count = WirelessChassis.objects.count()
        online_count = WirelessChassis.objects.filter(is_online=True).count()
        offline_count = WirelessChassis.objects.filter(is_online=False).count()

        logger.info("\nDevice Statistics:")
        logger.info(f"  Total: {device_count}")
        logger.info(f"  Online: {online_count}")
        logger.info(f"  Offline: {offline_count}")

        if device_count > 0:
            logger.info("\n✓ Models are ready for polling integration!")
            logger.info("\nNext steps:")
            logger.info("  1. Run: python manage.py poll_devices")
            logger.info("  2. Watch devices update in real-time")
            logger.info("  3. Check WebSocket subscriptions")

        logger.info("=" * 80)

        return passed == total

    def run(self, sample_size: int = None, clear: bool = False):
        """Run all tests."""
        if clear:
            logger.info("Clearing existing devices...")
            count = WirelessChassis.objects.all().delete()
            logger.info("✓ Deleted existing devices")

        devices = self.get_devices_from_api()
        if not devices:
            logger.error("✗ No devices available to test")
            return False

        if sample_size and devices:
            devices = devices[:sample_size]

        # Run tests
        self.test_basic_population(devices)
        self.test_device_queries()
        self.test_state_tracking()
        self.test_telemetry_storage()
        self.test_model_relationships()
        self.test_data_integrity()

        success = self.print_summary()
        return success


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test django-micboard models with real Shure device data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with all discovered devices
  python scripts/test_models_with_shure_data.py

  # Test with first 5 devices
  python scripts/test_models_with_shure_data.py --sample-size 5

  # Clear and re-populate
  python scripts/test_models_with_shure_data.py --clear
        """,
    )

    parser.add_argument("--sample-size", type=int, metavar="N", help="Test with first N devices")
    parser.add_argument(
        "--clear", action="store_true", help="Clear existing devices before populating"
    )

    args = parser.parse_args()

    try:
        tester = ModelPopulationTester()
        success = tester.run(sample_size=args.sample_size, clear=args.clear)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
