"""Service for refreshing discovered device records from manufacturer APIs."""

import logging
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.common.base.plugin import ManufacturerPlugin, get_manufacturer_plugin
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class DeviceRefreshService:
    """Refreshes discovered device records from manufacturer APIs."""

    def refresh_discovered_devices_from_api(
        self,
        queryset: Iterable[DiscoveredDevice],
    ) -> tuple[int, int]:
        """Refresh discovered device records from manufacturer APIs.

        Dispatches work to a per-device refresher helper to keep complexity low.
        Returns (updated_count, failed_count).
        """
        updated = 0
        failed = 0

        for discovered in queryset:
            ok = self._refresh_single_discovered_device(discovered)
            if ok:
                updated += 1
            else:
                failed += 1

        return updated, failed

    def _refresh_single_discovered_device(self, discovered: DiscoveredDevice) -> bool:
        """Refresh a single DiscoveredDevice record from its manufacturer's API.

        Returns True on success, False on failure.
        """
        try:
            manufacturer = discovered.manufacturer
            if manufacturer is None:
                logger.warning(
                    "DiscoveredDevice %s has no manufacturer; skipping",
                    discovered.pk,
                )
                return False

            plugin_cls = get_manufacturer_plugin(manufacturer.code)
            plugin = plugin_cls(manufacturer)

            device_data = self._get_device_data_from_plugin(plugin, discovered)
            if not device_data:
                logger.info(
                    "No device data found for discovered device %s (%s)",
                    discovered.pk,
                    discovered.ip,
                )
                return False

            self._enrich_device_with_channels(plugin, discovered, device_data)

            transformed = self._transform_device(plugin, device_data, discovered)
            if not transformed:
                discovered.metadata = device_data
                discovered.save()
                return False

            self._apply_transformed_to_discovered(discovered, transformed, device_data)
            discovered.save()
            return True

        except Exception as exc:
            logger.exception(
                "Exception while refreshing discovered device %s",
                discovered.pk,
                exc_info=sanitized_exception_info(exc),
            )
            return False

    def _get_device_data_from_plugin(
        self,
        plugin: ManufacturerPlugin,
        discovered: DiscoveredDevice,
    ) -> dict[str, Any] | None:
        """Attempt to obtain raw device data from plugin using best-effort lookups."""
        if discovered.api_device_id:
            try:
                dev = plugin.get_device(discovered.api_device_id)
                if dev:
                    return dev
            except Exception as exc:
                logger.exception(
                    "Plugin.get_device failed for %s (%s)",
                    discovered.api_device_id,
                    discovered.ip,
                    exc_info=sanitized_exception_info(exc),
                )

        try:
            devices = plugin.get_devices()
            for dev in devices:
                if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                    return dev
        except Exception as exc:
            logger.exception(
                "Plugin.get_devices failed for manufacturer %s",
                plugin.code,
                exc_info=sanitized_exception_info(exc),
            )

        return None

    def _enrich_device_with_channels(
        self,
        plugin: ManufacturerPlugin,
        discovered: DiscoveredDevice,
        device_data: dict[str, Any],
    ) -> None:
        """If available, fetch channel information and attach it to raw device_data."""
        if discovered.api_device_id:
            try:
                device_data["channels"] = plugin.get_device_channels(discovered.api_device_id)
            except Exception as exc:
                logger.exception(
                    "Could not fetch channels for device %s",
                    discovered.api_device_id,
                    exc_info=sanitized_exception_info(exc),
                )

    def _transform_device(
        self,
        plugin: ManufacturerPlugin,
        device_data: dict[str, Any],
        discovered: DiscoveredDevice,
    ) -> dict[str, Any] | None:
        """Transform raw device_data using manufacturer's plugin transformer."""
        try:
            return plugin.transform_device_data(device_data)
        except Exception as exc:
            logger.exception(
                "Error transforming discovered device %s",
                discovered.pk,
                exc_info=sanitized_exception_info(exc),
            )
        return None

    def _apply_transformed_to_discovered(
        self,
        discovered: DiscoveredDevice,
        transformed: dict[str, Any],
        device_data: dict[str, Any],
    ) -> None:
        """Apply transformed/normalized device data onto the DiscoveredDevice model instance."""
        discovered.metadata = device_data

        model = transformed.get("model")
        if model:
            discovered.model = model

        api_id = transformed.get("api_device_id")
        if api_id:
            discovered.api_device_id = api_id

        ch = transformed.get("channels")
        if ch is not None:
            with suppress(ValueError, TypeError):
                discovered.channels = int(ch)

        status_val = transformed.get("status")
        if isinstance(status_val, str):
            ts = status_val.lower()
            if ts in ("online", "ready", "up"):
                discovered.status = discovered.STATUS_READY
            elif ts in ("offline", "down"):
                discovered.status = discovered.STATUS_OFFLINE
            elif ts in ("error", "fault"):
                discovered.status = discovered.STATUS_ERROR
