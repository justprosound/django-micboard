import json
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Diagnose Shure API response structure, including frequencyBand."

    def handle(self, *args, **options):
        config = getattr(settings, "MICBOARD_CONFIG", {})
        base_url = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
        shared_key = config.get("SHURE_API_SHARED_KEY")
        verify_ssl = config.get("SHURE_API_VERIFY_SSL", False)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ("true", "1", "yes")
        if not shared_key:
            logger.error("SHURE_API_SHARED_KEY not configured")
            self.stderr.write(self.style.ERROR("SHURE_API_SHARED_KEY not configured"))
            return
        client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
        logger.info("=" * 80)
        logger.info("SHURE API STRUCTURE DIAGNOSTIC")
        logger.info("=" * 80)
        try:
            logger.info("\n1. Fetching devices...")
            devices = client.devices.get_devices()
            logger.info(f"✓ Got {len(devices)} devices")
            if not devices:
                logger.warning("No devices available")
                self.stderr.write(self.style.WARNING("No devices available"))
                return
            device_id = devices[0].get("id")
            logger.info(f"\n2. Inspecting first device: {device_id}")
            logger.info("\n3. Fetching device status (should contain frequencyBand)...")
            status = client.devices.get_device_status(device_id)
            if status:
                logger.info("✓ Status response received")
                logger.info("\n   Available fields in status:")
                for key in sorted(status.keys()):
                    value = status[key]
                    if isinstance(value, (dict, list)):
                        value_str = f"{type(value).__name__} ({len(value)} items)"
                    elif isinstance(value, str) and len(value) > 50:
                        value_str = f'"{value[:50]}..."'
                    else:
                        value_str = (
                            json.dumps(value) if not isinstance(value, str) else f'"{value}"'
                        )
                    logger.info(f"      • {key}: {value_str}")
                frequency_band = status.get("frequencyBand")
                if frequency_band is not None:
                    logger.info(f"\n   ✓ frequencyBand found: {frequency_band}")
                else:
                    logger.info("\n   ⚠ frequencyBand NOT found in status")
                    logger.info("     (May be available in other endpoints)")
            else:
                logger.warning("No status response")
            logger.info("\n4. Testing device enrichment...")
            enriched = client.devices._enrich_device_data(device_id, devices[0].copy())
            logger.info("   After enrichment:")
            if "frequency_band" in enriched:
                logger.info(f"      ✓ frequency_band: {enriched['frequency_band']}")
            else:
                logger.info("      ⚠ frequency_band: not populated")
            logger.info("\n5. WirelessChassis model information:")
            logger.info(f"      • model: {enriched.get('model', 'N/A')}")
            logger.info(f"      • model_variant: {enriched.get('model_variant', 'N/A')}")
            logger.info(f"      • serial_number: {enriched.get('serial_number', 'N/A')}")
            logger.info(f"      • firmware_version: {enriched.get('firmware_version', 'N/A')}")
            logger.info("\n" + "=" * 80)
            logger.info("SUMMARY")
            logger.info("=" * 80)
            if status and status.get("frequencyBand"):
                logger.info(f"✓ API provides frequencyBand = '{status['frequencyBand']}'")
                logger.info("✓ Ready for band plan auto-detection")
            else:
                logger.info("ℹ  API doesn't provide frequencyBand in status")
                logger.info("ℹ  Fallback to model code detection available")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback

            traceback.print_exc()
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
