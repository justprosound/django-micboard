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
            logger.info("✓ Got %s devices", len(devices))
            if not devices:
                logger.warning("No devices available")
                self.stderr.write(self.style.WARNING("No devices available"))
                return
            device_id = devices[0].get("id")
            logger.info("\n2. Inspecting first device: %s", device_id)
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
                    logger.info("      • %s: %s", key, value_str)
                frequency_band = status.get("frequencyBand")
                if frequency_band is not None:
                    logger.info("\n   ✓ frequencyBand found: %s", frequency_band)
                else:
                    logger.info("\n   ⚠ frequencyBand NOT found in status")
                    logger.info("     (May be available in other endpoints)")
            else:
                logger.warning("No status response")
            logger.info("\n4. Testing device enrichment...")
            enriched = client.devices._enrich_device_data(device_id, devices[0].copy())
            logger.info("   After enrichment:")
            if "frequency_band" in enriched:
                logger.info("      ✓ frequency_band: %s", enriched["frequency_band"])
            else:
                logger.info("      ⚠ frequency_band: not populated")
            logger.info("\n5. WirelessChassis model information:")
            logger.info("      • model: %s", enriched.get("model", "N/A"))
            logger.info("      • model_variant: %s", enriched.get("model_variant", "N/A"))
            logger.info("      • serial_number: %s", enriched.get("serial_number", "N/A"))
            logger.info("      • firmware_version: %s", enriched.get("firmware_version", "N/A"))
            logger.info("\n" + "=" * 80)
            logger.info("SUMMARY")
            logger.info("=" * 80)
            if status and status.get("frequencyBand"):
                logger.info("✓ API provides frequencyBand = '%s'", status["frequencyBand"])
                logger.info("✓ Ready for band plan auto-detection")
            else:
                logger.info("ℹ  API doesn't provide frequencyBand in status")
                logger.info("ℹ  Fallback to model code detection available")
            logger.info("=" * 80)
        except Exception as e:
            logger.error("Error: %s", e)
            import traceback

            traceback.print_exc()
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
