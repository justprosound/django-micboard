"""
Device management service for django-micboard.

Handles device lifecycle operations (CRUD, state management, synchronization)
across all manufacturers. Separates business logic from HTTP clients.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.utils import timezone

if TYPE_CHECKING:
    from micboard.manufacturers.base import BaseAPIClient, BaseManufacturerPlugin
    from micboard.models import Manufacturer, Receiver, Transmitter

logger = logging.getLogger(__name__)


class DeviceService:
    """
    Service for managing device lifecycle operations.

    Provides high-level API for device synchronization, state management,
    and data enrichment. Uses manufacturer-specific clients internally
    but presents a unified interface.
    """

    def __init__(
        self,
        manufacturer: Manufacturer,
        client: BaseAPIClient | None = None,
        plugin: BaseManufacturerPlugin | None = None,
    ):
        """
        Initialize device service for a manufacturer.

        Args:
            manufacturer: Manufacturer instance
            client: Optional API client (for testing/dependency injection)
            plugin: Optional manufacturer plugin (for testing)
        """
        self.manufacturer = manufacturer

        # Use provided client/plugin or get default from manufacturer
        if plugin:
            self.plugin = plugin
            self.client = client or plugin.get_client()
        elif client:
            self.plugin = None
            self.client = client
        else:
            # Get plugin and client from manufacturer
            from micboard.manufacturers import get_manufacturer_plugin

            plugin_class = get_manufacturer_plugin(manufacturer.code)
            self.plugin = plugin_class(manufacturer)
            self.client = self.plugin.get_client()

    def sync_devices_from_api(self) -> tuple[int, int]:
        """
        Synchronize devices from manufacturer API to Django models.

        Fetches device list from API, creates/updates Receiver objects,
        and returns counts of created and updated devices.

        Returns:
            Tuple of (created_count, updated_count)
        """
        from micboard.models import Receiver

        try:
            # Fetch devices from API using client
            api_devices = self.client.get_devices()
            if not api_devices:
                logger.info("No devices returned from API for %s", self.manufacturer.name)
                return 0, 0

            created_count = 0
            updated_count = 0

            for device_data in api_devices:
                device_id = device_data.get("id") or device_data.get("api_device_id")
                if not device_id:
                    logger.warning("Device missing ID field: %s", device_data)
                    continue

                # Extract key fields (handle different manufacturer formats)
                ip = (
                    device_data.get("ip")
                    or device_data.get("ipAddress")
                    or device_data.get("ipv4")
                )
                name = device_data.get("name") or device_data.get("model") or ""
                model = device_data.get("model") or ""
                firmware = (
                    device_data.get("firmware")
                    or device_data.get("firmware_version")
                    or device_data.get("firmwareVersion")
                    or ""
                )

                # Create or update receiver
                receiver, created = Receiver.objects.update_or_create(
                    api_device_id=device_id,
                    manufacturer=self.manufacturer,
                    defaults={
                        "ip": ip,
                        "name": name,
                        "model": model,
                        "firmware": firmware,
                        "last_seen": timezone.now(),
                    },
                )

                # Use lifecycle manager for state transition
                from micboard.services.device_lifecycle import get_lifecycle_manager
                lifecycle = get_lifecycle_manager(self.manufacturer.code)
                
                if created:
                    # New device: mark as online
                    lifecycle.mark_online(receiver)
                    created_count += 1
                    logger.info(
                        "Created receiver %s (%s) for %s", name, ip, self.manufacturer.name
                    )
                else:
                    # Existing device: update last_seen and ensure online
                    receiver.last_seen = timezone.now()
                    receiver.save(update_fields=['last_seen'])
                    # Only transition to online if not already in a stable state
                    if receiver.status not in {'online', 'degraded', 'maintenance'}:
                        lifecycle.mark_online(receiver)
                    updated_count += 1
                    logger.debug(
                        "Updated receiver %s (%s) for %s", name, ip, self.manufacturer.name
                    )

            logger.info(
                "Synced %d devices for %s: %d created, %d updated",
                len(api_devices),
                self.manufacturer.name,
                created_count,
                updated_count,
            )

            return created_count, updated_count

        except Exception:
            logger.exception("Error syncing devices from API for %s", self.manufacturer.name)
            return 0, 0

    def get_active_devices(self) -> list[Receiver]:
        """
        Get all active devices for this manufacturer.

        Returns:
            List of Receiver objects
        """
        from micboard.models import Receiver
        from micboard.services.device_lifecycle import DeviceStatus

        active_statuses = DeviceStatus.active_states()
        return cast(
            list[Receiver],
            list(Receiver.objects.filter(manufacturer=self.manufacturer, status__in=active_statuses)),
        )

    def get_device_by_api_id(self, api_device_id: str) -> Receiver | None:
        """
        Get device by manufacturer's API device ID.

        Args:
            api_device_id: Device ID from manufacturer API

        Returns:
            Receiver instance or None
        """
        from micboard.models import Receiver

        try:
            return cast(
                Receiver,
                Receiver.objects.get(
                    api_device_id=api_device_id, manufacturer=self.manufacturer
                ),
            )
        except Receiver.DoesNotExist:
            return None

    def update_device_state(self, device_id: int, state: dict[str, Any]) -> bool:
        """
        Update device state attributes.

        Args:
            device_id: Django Receiver primary key
            state: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        from micboard.models import Receiver

        try:
            receiver = Receiver.objects.get(pk=device_id, manufacturer=self.manufacturer)

            for key, value in state.items():
                if hasattr(receiver, key):
                    setattr(receiver, key, value)

            receiver.save()
            logger.debug("Updated device %s state: %s", device_id, state)
            return True

        except Receiver.DoesNotExist:
            logger.warning("Device %s not found for state update", device_id)
            return False
        except Exception:
            logger.exception("Error updating device %s state", device_id)
            return False

    def mark_online(self, device_id: int) -> bool:
        """
        Mark device as online using lifecycle manager.

        Args:
            device_id: Django Receiver primary key

        Returns:
            True if successful
        """
        try:
            from micboard.models import Receiver
            from micboard.services.device_lifecycle import get_lifecycle_manager

            receiver = Receiver.objects.get(pk=device_id, manufacturer=self.manufacturer)
            lifecycle = get_lifecycle_manager(self.manufacturer.code)
            lifecycle.mark_online(receiver)
            return True
        except Exception:
            logger.exception("Error marking device %s as online", device_id)
            return False

    def mark_offline(self, device_id: int) -> bool:
        """
        Mark device as offline using lifecycle manager.

        Args:
            device_id: Django Receiver primary key

        Returns:
            True if successful
        """
        try:
            from micboard.models import Receiver
            from micboard.services.device_lifecycle import get_lifecycle_manager

            receiver = Receiver.objects.get(pk=device_id, manufacturer=self.manufacturer)
            lifecycle = get_lifecycle_manager(self.manufacturer.code)
            lifecycle.mark_offline(receiver, reason="Device not found in API poll")
            return True
        except Exception:
            logger.exception("Error marking device %s as offline", device_id)
            return False

    def enrich_device_data(self, api_device_id: str) -> dict[str, Any] | None:
        """
        Fetch enriched device data from manufacturer API.

        Calls optional endpoints like /identify, /network, /status
        to get additional metadata (serial, MAC, hostname, etc.).

        Args:
            api_device_id: Device ID from manufacturer API

        Returns:
            Enriched device data dict or None
        """
        try:
            # Get base device data
            device_data = self.client.get_device(api_device_id)
            if not device_data:
                logger.warning("No device data for %s", api_device_id)
                return None

            # Use client's enrichment if available (Shure/Sennheiser specific)
            if hasattr(self.client, "_enrich_device_data"):
                device_data = self.client._enrich_device_data(api_device_id, device_data)

            return cast(dict[str, Any], device_data)

        except Exception:
            logger.exception("Error enriching device data for %s", api_device_id)
            return None

    def get_device_channels(self, api_device_id: str) -> list[dict[str, Any]]:
        """
        Get channel/transmitter data for a device.

        Args:
            api_device_id: Device ID from manufacturer API

        Returns:
            List of channel data dictionaries
        """
        try:
            if hasattr(self.client, "get_device_channels"):
                channels = self.client.get_device_channels(api_device_id)
                return channels or []
            return []
        except Exception:
            logger.exception("Error getting channels for device %s", api_device_id)
            return []

    def get_transmitter_data(self, api_device_id: str, channel: int) -> dict[str, Any] | None:
        """
        Get transmitter data for a specific channel.

        Args:
            api_device_id: Device ID from manufacturer API
            channel: Channel number

        Returns:
            Transmitter data dict or None
        """
        try:
            if hasattr(self.client, "get_transmitter_data"):
                return cast(
                    dict[str, Any] | None,
                    self.client.get_transmitter_data(api_device_id, channel),
                )
            return None
        except Exception:
            logger.exception("Error getting transmitter data for %s ch%d", api_device_id, channel)
            return None

    def sync_transmitters_for_device(self, receiver: Receiver) -> int:
        """
        Synchronize transmitters for a specific receiver.

        Args:
            receiver: Receiver instance

        Returns:
            Number of transmitters synced
        """
        from micboard.models import Transmitter

        if not receiver.api_device_id:
            logger.warning("Receiver %s missing api_device_id", receiver.id)
            return 0

        try:
            channels = self.get_device_channels(receiver.api_device_id)
            synced_count = 0

            for channel_data in channels:
                channel_num = channel_data.get("channel") or channel_data.get("channelNumber")
                if not channel_num:
                    continue

                # Get transmitter-specific data
                tx_data = channel_data.get("transmitter") or channel_data.get("tx")
                if not tx_data:
                    # Try fetching from dedicated endpoint
                    tx_data = self.get_transmitter_data(receiver.api_device_id, channel_num)

                if tx_data:
                    # Create or update transmitter
                    Transmitter.objects.update_or_create(
                        receiver=receiver,
                        channel=channel_num,
                        defaults={
                            "model": tx_data.get("model") or "",
                            "battery_level": tx_data.get("battery") or tx_data.get("batteryLevel"),
                            "rssi": tx_data.get("rssi"),
                            "frequency": channel_data.get("frequency"),
                        },
                    )
                    synced_count += 1

            logger.debug(
                "Synced %d transmitters for receiver %s", synced_count, receiver.api_device_id
            )
            return synced_count

        except Exception:
            logger.exception("Error syncing transmitters for receiver %s", receiver.id)
            return 0

    def poll_and_sync_all(self) -> dict[str, Any]:
        """
        Comprehensive polling: sync devices and transmitters.

        Performs full synchronization from API:
        1. Sync devices (receivers)
        2. Sync transmitters for each device
        3. Return summary statistics

        Returns:
            Dictionary with sync statistics
        """
        result = {
            "manufacturer": self.manufacturer.code,
            "devices_created": 0,
            "devices_updated": 0,
            "transmitters_synced": 0,
            "errors": [],
        }

        try:
            # Sync devices
            created, updated = self.sync_devices_from_api()
            result["devices_created"] = created
            result["devices_updated"] = updated

            # Sync transmitters for each device
            receivers = self.get_active_devices()
            for receiver in receivers:
                try:
                    tx_count = self.sync_transmitters_for_device(receiver)
                    result["transmitters_synced"] += tx_count
                except Exception as e:
                    result["errors"].append(f"Failed to sync transmitters for {receiver.id}: {e}")

            logger.info(
                "Polling complete for %s: %d devices, %d transmitters",
                self.manufacturer.name,
                created + updated,
                result["transmitters_synced"],
            )

        except Exception as e:
            error_msg = f"Polling failed for {self.manufacturer.name}: {e}"
            result["errors"].append(error_msg)
            logger.exception(error_msg)

        return result


# Convenience function for quick access
def get_device_service(manufacturer: Manufacturer) -> DeviceService:
    """
    Get a DeviceService instance for a manufacturer.

    Args:
        manufacturer: Manufacturer instance

    Returns:
        DeviceService instance
    """
    return DeviceService(manufacturer)
