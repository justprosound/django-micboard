"""Service for fetching device details from manufacturer plugins."""

import logging

from micboard.integrations.common import get_manufacturer_plugin
from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)


class DeviceDetailService:
    """Fetches device details via manufacturer plugins."""

    def get_device_detail(
        self,
        *,
        manufacturer_code: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, dict]:
        """Fetch device detail via manufacturer plugins.

        Args:
            manufacturer_code: Optional code to scope the lookup. If omitted,
                              all manufacturers are queried.
            device_id: Device identifier from the manufacturer's API.

        Returns:
            Mapping of manufacturer code -> {status, device|error}
        """
        if not device_id:
            return {}

        if manufacturer_code:
            manufacturers = Manufacturer.objects.filter(code=manufacturer_code)
        else:
            manufacturers = Manufacturer.objects.all()

        results: dict[str, dict] = {}

        for mfr in manufacturers:
            try:
                plugin_cls = get_manufacturer_plugin(mfr.code)
                plugin = plugin_cls(mfr)

                dev = plugin.get_device(device_id)
                if not dev:
                    continue

                try:
                    channels = plugin.get_device_channels(device_id)
                    dev["channels"] = channels
                except Exception:
                    logger.debug("No channel data for %s", device_id)

                transformed = plugin.transform_device_data(dev)
                if not transformed:
                    results[mfr.code] = {"status": "error", "error": "transform failed"}
                    continue

                results[mfr.code] = {"status": "success", "device": transformed}

                if manufacturer_code:
                    return results

            except Exception as exc:
                logger.exception("Error fetching device %s for %s: %s", device_id, mfr.code, exc)
                results[mfr.code] = {"status": "error", "error": str(exc)}

        return results
