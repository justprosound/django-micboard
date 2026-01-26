#!/usr/bin/env python
"""Test band plan auto-detection from Shure System API.

This script connects to the Shure System API, fetches real receiver devices,
and tests the new band plan detection functions to verify:
  1. API provides frequencyBand data
  2. detect_band_plan_from_api_data() correctly normalizes it
  3. Frequencies are correctly auto-populated

Usage:
    python scripts/test_band_plan_detection.py

Environment Variables:
    MICBOARD_SHURE_API_SHARED_KEY  - API shared key (REQUIRED)
"""

import logging
import os
import sys

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
import django

django.setup()

from django.conf import settings

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.models import Manufacturer, WirelessChassis

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class BandPlanDetectionTester:
    """Test band plan detection from real Shure API data."""

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

    def fetch_real_devices(self):
        """Fetch real receiver devices from Shure API."""
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Fetch Real Devices from Shure System API")
        logger.info("=" * 80)

        try:
            devices = self.client.devices.get_devices()
            logger.info(f"✓ Retrieved {len(devices)} devices from API")

            # Show first 5 devices
            for idx, device in enumerate(devices[:5], 1):
                device_id = device.get("id", "N/A")
                model = device.get("model", "N/A")
                logger.info(f"  Device {idx}: id={device_id}, model={model}")

            if len(devices) > 5:
                logger.info(f"  ... and {len(devices) - 5} more")

            return devices
        except Exception as e:
            logger.error(f"✗ Failed to fetch devices: {e}")
            return []

    def enrich_device_status(self, devices):
        """Enrich devices with status data including frequencyBand.

        This simulates what happens during actual device sync.
        """
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Enrich Devices with Status Data (including frequencyBand)")
        logger.info("=" * 80)

        enriched = []
        for device in devices[:5]:  # Test with first 5
            device_id = device.get("id")
            if not device_id:
                continue

            # Get device status (which includes frequencyBand)
            status = self.client.devices.get_device_status(device_id)
            if not status:
                logger.warning(f"  ⚠ No status available for {device_id}")
                continue

            # Add frequencyBand to device data
            frequency_band = status.get("frequencyBand")
            device["frequencyBand"] = frequency_band
            device["frequency_band"] = frequency_band  # Normalize field name

            logger.info(
                f"✓ {device_id}: frequencyBand = {frequency_band or '(not provided in status)'}"
            )
            enriched.append(device)

        return enriched

    def test_detection_functions(self, devices):
        """Test the band plan detection functions."""
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Test Band Plan Detection Functions")
        logger.info("=" * 80)

        shure = Manufacturer.objects.get(code="shure")
        detection_tests = []

        for device in devices:
            device_id = device.get("id")
            model = device.get("model", "Unknown")
            frequency_band = device.get("frequencyBand")

            logger.info(f"\n  Testing device: {device_id} ({model})")
            logger.info(f"    API frequencyBand: {frequency_band or '(not provided)'}")

            # Create a temporary WirelessChassis instance
            chassis = WirelessChassis(
                manufacturer=shure,
                model=model,
                api_device_id=device_id,
                ip="192.168.1.1",  # Dummy IP
                name=f"Test {device_id}",
            )

            # Test detection
            result = chassis.detect_band_plan_from_api_data(api_band_value=frequency_band)

            logger.info("    Detection result:")
            logger.info(f"      • band_plan_name: {result.get('band_plan_name')}")
            logger.info(f"      • band_plan_min_mhz: {result.get('band_plan_min_mhz')}")
            logger.info(f"      • band_plan_max_mhz: {result.get('band_plan_max_mhz')}")
            logger.info(f"      • source: {result.get('source')}")
            logger.info(f"      • message: {result.get('message')}")

            detection_tests.append(
                {
                    "device_id": device_id,
                    "model": model,
                    "api_frequency_band": frequency_band,
                    "detection_result": result,
                    "success": result.get("band_plan_name") is not None,
                }
            )

        return detection_tests

    def test_apply_and_save(self, devices):
        """Test applying detected band plan and saving to database."""
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Test Apply and Save to Database")
        logger.info("=" * 80)

        shure = Manufacturer.objects.get(code="shure")
        saved_devices = []

        for device in devices[:3]:  # Test with first 3
            device_id = device.get("id")
            model = device.get("model", "Unknown")
            frequency_band = device.get("frequencyBand")

            logger.info(f"\n  Saving device: {device_id} ({model})")
            logger.info(f"    Original frequencyBand: {frequency_band or '(not provided)'}")

            try:
                # Create and save WirelessChassis
                chassis = WirelessChassis.objects.create(
                    manufacturer=shure,
                    model=model,
                    api_device_id=device_id,
                    ip=f"192.168.1.{len(saved_devices) + 1}",  # Dummy increment
                    name=f"Detection Test {device_id}",
                    role="receiver",
                )

                # Apply detection
                if chassis.apply_detected_band_plan(api_band_value=frequency_band):
                    logger.info("    ✓ Band plan detected and applied")
                    logger.info(f"      • band_plan_name: {chassis.band_plan_name}")
                    logger.info(f"      • band_plan_min_mhz: {chassis.band_plan_min_mhz}")
                    logger.info(f"      • band_plan_max_mhz: {chassis.band_plan_max_mhz}")
                else:
                    logger.warning("    ⚠ Could not detect band plan")

                # Save changes
                chassis.save()
                logger.info(f"    ✓ Saved to database (ID: {chassis.id})")

                saved_devices.append(
                    {
                        "id": chassis.id,
                        "device_id": device_id,
                        "model": model,
                        "band_plan_name": chassis.band_plan_name,
                        "band_plan_min_mhz": chassis.band_plan_min_mhz,
                        "band_plan_max_mhz": chassis.band_plan_max_mhz,
                    }
                )
            except Exception as e:
                logger.error(f"    ✗ Failed to save: {e}")

        return saved_devices

    def print_summary(self, detection_tests, saved_devices):
        """Print comprehensive test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)

        # Detection test results
        logger.info("\n1. Band Plan Detection Results:")
        successful = sum(1 for test in detection_tests if test["success"])
        logger.info(f"   Successful detections: {successful}/{len(detection_tests)}")

        for test in detection_tests:
            if test["success"]:
                logger.info(
                    f"   ✓ {test['device_id']} ({test['model']}): {test['detection_result'].get('band_plan_name')}"
                )
            else:
                logger.info(
                    f"   ⚠ {test['device_id']} ({test['model']}): {test['detection_result'].get('message')}"
                )

        # Saved devices
        logger.info(f"\n2. Saved to Database: {len(saved_devices)} devices")
        for device in saved_devices:
            if device["band_plan_name"]:
                logger.info(
                    f"   ✓ {device['device_id']}: {device['band_plan_name']} ({device['band_plan_min_mhz']}-{device['band_plan_max_mhz']} MHz)"
                )
            else:
                logger.info(f"   ⚠ {device['device_id']}: No band plan")

        # Key findings
        logger.info("\n3. Key Findings:")
        api_provides_band = sum(
            1 for test in detection_tests if test["api_frequency_band"] is not None
        )
        logger.info(f"   • API provides frequencyBand: {api_provides_band}/{len(detection_tests)}")

        if api_provides_band > 0:
            logger.info("     ✓ API data available for band plan detection")
        else:
            logger.info("     ℹ  API doesn't provide frequencyBand, using model fallback")

        logger.info(
            f"   • Detection success rate: {successful}/{len(detection_tests)} ({100 * successful // len(detection_tests)}%)"
        )
        logger.info(f"   • Database writes: {len(saved_devices)} devices")

        logger.info("\n4. Conclusion:")
        if successful > 0 and len(saved_devices) > 0:
            logger.info("   ✓ Band plan auto-detection is working!")
            logger.info("   ✓ Next step: Integrate into device sync workflow")
        else:
            logger.info("   ⚠ Band plan detection needs investigation")

        logger.info("=" * 80)

    def run(self):
        """Run all tests."""
        logger.info("=" * 80)
        logger.info("BAND PLAN AUTO-DETECTION TEST")
        logger.info("=" * 80)

        try:
            # Step 1: Fetch devices
            devices = self.fetch_real_devices()
            if not devices:
                logger.error("No devices available to test")
                return False

            # Step 2: Enrich with status data
            enriched = self.enrich_device_status(devices)
            if not enriched:
                logger.error("No enriched device data available")
                return False

            # Step 3: Test detection functions
            detection_tests = self.test_detection_functions(enriched)

            # Step 4: Test apply and save
            saved_devices = self.test_apply_and_save(enriched)

            # Summary
            self.print_summary(detection_tests, saved_devices)

            return True
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            import traceback

            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    try:
        tester = BandPlanDetectionTester()
        success = tester.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Setup error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
