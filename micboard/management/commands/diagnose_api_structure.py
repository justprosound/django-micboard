import json
import logging

from django.core.management.base import BaseCommand

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.services.settings import settings

logger = logging.getLogger(__name__)


def _format_status_value(value):
    if isinstance(value, (dict, list)):
        return f"{type(value).__name__} ({len(value)} items)"
    if isinstance(value, str):
        return f'"{value[:50]}..."' if len(value) > 50 else f'"{value}"'
    return json.dumps(value)


def _log_device_status(status) -> None:
    if not status:
        logger.warning("No status response")
        return

    logger.info("✓ Status response received")
    logger.info("\n   Available fields in status:")
    for key in sorted(status):
        logger.info("      • %s: %s", key, _format_status_value(status[key]))

    frequency_band = status.get("frequencyBand")
    if frequency_band is not None:
        logger.info("\n   ✓ frequencyBand found: %s", frequency_band)
    else:
        logger.info("\n   ⚠ frequencyBand NOT found in status")
        logger.info("     (May be available in other endpoints)")


def _log_enriched_device(enriched) -> None:
    logger.info("   After enrichment:")
    if "frequency_band" in enriched:
        logger.info("      ✓ frequency_band: %s", enriched["frequency_band"])
    else:
        logger.info("      ⚠ frequency_band: not populated")
    logger.info("\n5. WirelessChassis model information:")
    for field in ("model", "model_variant", "serial_number", "firmware_version"):
        logger.info("      • %s: %s", field, enriched.get(field, "N/A"))


def _log_summary(status) -> None:
    logger.info("\n%s", "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    if status and status.get("frequencyBand"):
        logger.info("✓ API provides frequencyBand = '%s'", status["frequencyBand"])
        logger.info("✓ Ready for band plan auto-detection")
    else:
        logger.info("API does not provide frequencyBand in status")
        logger.info("Fallback to model code detection is available")
    logger.info("=" * 80)


def _run_diagnostic(client, stderr, style) -> None:
    logger.info("\n1. Fetching devices...")
    devices = client.devices.get_devices()
    logger.info("✓ Got %s devices", len(devices))
    if not devices:
        logger.warning("No devices available")
        stderr.write(style.WARNING("No devices available"))
        return

    device_id = devices[0].get("id")
    logger.info("\n2. Inspecting first device: %s", device_id)
    logger.info("\n3. Fetching device status (should contain frequencyBand)...")
    status = client.devices.get_device_status(device_id)
    _log_device_status(status)
    logger.info("\n4. Testing device enrichment...")
    enriched = client.devices._enrich_device_data(device_id, devices[0].copy())
    _log_enriched_device(enriched)
    _log_summary(status)


class Command(BaseCommand):
    help = "Diagnose Shure API response structure, including frequencyBand."

    def handle(self, *args, **options):
        base_url = settings.get("SHURE_API_BASE_URL", "https://localhost:10000")
        shared_key = settings.get("SHURE_API_SHARED_KEY")
        verify_ssl = settings.get("SHURE_API_VERIFY_SSL", False)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ("true", "1", "yes")
        if not shared_key:
            logger.error("SHURE_API_SHARED_KEY not configured")
            self.stderr.write(self.style.ERROR("SHURE_API_SHARED_KEY not configured"))
            return
        client = ShureSystemAPIClient(base_url=base_url, verify_ssl=verify_ssl)
        logger.info("%s\nSHURE API STRUCTURE DIAGNOSTIC\n%s", "=" * 80, "=" * 80)
        try:
            _run_diagnostic(client, self.stderr, self.style)
        except Exception as exc:
            logger.exception("Shure API diagnostic failed")
            self.stderr.write(self.style.ERROR(f"Error: {exc}"))
