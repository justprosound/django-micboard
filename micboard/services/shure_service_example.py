"""
Example: Shure Service with bi-directional sync and lifecycle management.

This demonstrates how to implement a manufacturer service using the new
DeviceLifecycleManager instead of signals for state management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction

from micboard.integrations.shure import ShureClient
from micboard.models import Manufacturer, Receiver, Channel, Transmitter
from micboard.services.manufacturer_service import ManufacturerService
from micboard.services.logging import get_structured_logger

logger = logging.getLogger(__name__)


class ShureService(ManufacturerService):
    """
    Shure manufacturer service with full lifecycle and bi-directional sync.

    Key Features:
    - Direct device lifecycle management (no signal-based business logic)
    - Bi-directional sync: pull from API, push to API
    - Automatic health monitoring and state transitions
    - Structured logging and audit trail
    """

    MANUFACTURER_CODE = "shure"
    MANUFACTURER_NAME = "Shure Incorporated"
    DEFAULT_POLL_INTERVAL = 30
    SUPPORTS_DISCOVERY = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._structured_logger = get_structured_logger()

    def get_client(self) -> Optional[ShureClient]:
        """Get or create Shure API client."""
        if not self._client:
            from django.conf import settings

            shure_config = getattr(settings, "MICBOARD_CONFIG", {})
            base_url = shure_config.get("SHURE_API_BASE_URL")
            shared_key = shure_config.get("SHURE_API_SHARED_KEY")

            if not base_url:
                logger.error("SHURE_API_BASE_URL not configured")
                return None

            self._client = ShureClient(
                base_url=base_url,
                shared_key=shared_key,
                timeout=shure_config.get("SHURE_API_TIMEOUT", 10),
                verify_ssl=shure_config.get("SHURE_API_VERIFY_SSL", True),
            )

        return self._client

    def poll_devices(self) -> List[Dict[str, Any]]:
        """
        Poll Shure API for all devices and update database.

        Returns:
            List of device dicts in standard format
        """
        try:
            client = self.get_client()
            if not client:
                logger.error("Cannot poll devices: client not available")
                return []

            # Start sync log
            sync_log = self._structured_logger.log_sync_start(
                self.code, sync_type="full"
            )

            # Fetch devices from API
            api_devices = client.list_devices()
            logger.info(
                f"Fetched {len(api_devices)} devices from Shure API",
                extra={"service": self.code, "device_count": len(api_devices)},
            )

            # Get manufacturer instance
            manufacturer = Manufacturer.objects.get(code=self.code)

            # Track counts for sync result
            device_count = 0
            online_count = 0
            offline_count = 0
            updated_count = 0

            # Process each device
            for api_device in api_devices:
                try:
                    receiver = self._sync_receiver(manufacturer, api_device)
                    if receiver:
                        device_count += 1
                        
                        # Check health and auto-transition
                        health = self.check_device_health(receiver)
                        
                        if health == "online":
                            online_count += 1
                        elif health == "offline":
                            offline_count += 1
                        
                        # Sync channels/transmitters
                        if receiver.status == "online":
                            channels_updated = self._sync_channels(receiver, api_device)
                            if channels_updated:
                                updated_count += 1

                except Exception as e:
                    logger.error(
                        f"Error syncing device {api_device.get('id')}: {e}",
                        exc_info=True,
                        extra={"api_device_id": api_device.get("id")},
                    )

            # Complete sync log
            self._structured_logger.log_sync_complete(
                sync_log,
                device_count=device_count,
                online_count=online_count,
                offline_count=offline_count,
                updated_count=updated_count,
            )

            # Emit sync complete signal for UI notification
            self.emit_sync_complete({
                "device_count": device_count,
                "online_count": online_count,
                "offline_count": offline_count,
                "updated_count": updated_count,
                "status": "success",
            })

            # Update poll tracking
            self._last_poll = self._structured_logger.log_sync_start(
                self.code
            ).started_at
            self._poll_count += 1

            return api_devices

        except Exception as e:
            logger.error(
                f"Error polling Shure devices: {e}",
                exc_info=True,
                extra={"service": self.code},
            )
            self._error_count += 1
            return []

    @transaction.atomic
    def _sync_receiver(
        self, manufacturer: Manufacturer, api_device: Dict[str, Any]
    ) -> Optional[Receiver]:
        """
        Sync a receiver from API data.

        Uses DeviceLifecycleManager for all state changes.
        """
        api_device_id = api_device.get("id")
        ip = api_device.get("ip")

        if not api_device_id or not ip:
            logger.warning(f"Invalid device data: {api_device}")
            return None

        # Get or create receiver
        receiver, created = Receiver.objects.get_or_create(
            manufacturer=manufacturer,
            api_device_id=api_device_id,
            defaults={
                "ip": ip,
                "device_type": self._map_device_type(api_device.get("model", "")),
                "name": api_device.get("name", f"Receiver {api_device_id}"),
                "status": "discovered",  # Initial state
            },
        )

        if created:
            # Log creation
            self._structured_logger.log_crud_create(receiver)
            logger.info(
                f"Created new receiver: {receiver.name}",
                extra={"receiver_id": receiver.pk, "api_device_id": api_device_id},
            )

        # Update from API (handles state transition internally)
        self.update_device_from_api(receiver, api_device)

        return receiver

    def _sync_channels(
        self, receiver: Receiver, api_device: Dict[str, Any]
    ) -> bool:
        """
        Sync channels and transmitters for a receiver.

        Returns:
            True if any updates were made
        """
        updated = False
        api_channels = api_device.get("channels", [])

        for api_channel in api_channels:
            try:
                channel_num = api_channel.get("channel_number")
                if not channel_num:
                    continue

                # Get or create channel
                channel, created = Channel.objects.get_or_create(
                    receiver=receiver,
                    channel_number=channel_num,
                    defaults={"name": api_channel.get("name", f"Ch {channel_num}")},
                )

                # Update transmitter if present
                tx_data = api_channel.get("transmitter")
                if tx_data:
                    transmitter, tx_created = Transmitter.objects.get_or_create(
                        channel=channel,
                        defaults={
                            "slot": api_channel.get("slot", channel_num),
                            "lifecycle_status": "online",
                        },
                    )

                    # Update transmitter data
                    old_battery = transmitter.battery
                    transmitter.battery = tx_data.get("battery", 255)
                    transmitter.battery_charge = tx_data.get("battery_charge")
                    transmitter.audio_level = tx_data.get("audio_level", 0)
                    transmitter.rf_level = tx_data.get("rf_level", 0)
                    transmitter.frequency = tx_data.get("frequency", "")
                    transmitter.quality = tx_data.get("quality", 255)
                    transmitter.name = tx_data.get("name", "")
                    transmitter.last_seen = receiver.last_seen
                    transmitter.save()

                    if old_battery != transmitter.battery:
                        updated = True

            except Exception as e:
                logger.error(
                    f"Error syncing channel {channel_num}: {e}",
                    exc_info=True,
                    extra={"receiver_id": receiver.pk, "channel_num": channel_num},
                )

        return updated

    def get_device_details(self, device_id: str) -> Dict[str, Any]:
        """Fetch detailed information for a specific device."""
        client = self.get_client()
        if not client:
            return {}

        return client.get_device(device_id)

    def transform_device_data(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Shure API data to standard format.

        Standard format used by DeviceLifecycleManager.
        """
        return {
            "id": api_data.get("id"),
            "name": api_data.get("name", ""),
            "model": api_data.get("model", ""),
            "ip": api_data.get("ip", ""),
            "state": api_data.get("state", "UNKNOWN"),
            "firmware_version": api_data.get("firmware_version", ""),
            "serial_number": api_data.get("serial_number", ""),
            "properties": {
                "channels": api_data.get("channels", []),
                "network_interface": api_data.get("network_interface", {}),
            },
        }

    def configure_discovery(self, ips: List[str]) -> bool:
        """Configure Shure discovery with IP addresses."""
        client = self.get_client()
        if not client:
            return False

        try:
            # Push IPs to Shure System API discovery endpoint
            success = client.configure_discovery(ips)

            if success:
                logger.info(
                    f"Configured discovery with {len(ips)} IPs",
                    extra={"service": self.code, "ip_count": len(ips)},
                )
                
                # Log configuration change
                from micboard.models import ActivityLog
                ActivityLog.log_service(
                    operation=ActivityLog.UPDATE,
                    service_code=self.code,
                    summary=f"Discovery configured with {len(ips)} IPs",
                    status="success",
                    details={"ip_count": len(ips), "ips": ips[:10]},  # First 10 for brevity
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to configure discovery: {e}",
                exc_info=True,
                extra={"service": self.code},
            )
            return False

    def push_configuration_to_device(
        self, receiver: Receiver, config: Dict[str, Any]
    ) -> bool:
        """
        Push configuration changes to a device (bi-directional sync).

        Example configs:
        - {'name': 'New Device Name'}
        - {'network': {'dhcp': True}}
        - {'channels': [{'channel_number': 1, 'frequency': '542.125'}]}
        """
        client = self.get_client()
        if not client:
            return False

        try:
            # Push config to API
            success = client.update_device(receiver.api_device_id, config)

            if success:
                # Sync local model to match
                if "name" in config:
                    receiver.name = config["name"]
                    receiver.save(update_fields=["name", "updated_at"])

                logger.info(
                    f"Pushed configuration to {receiver.name}",
                    extra={
                        "receiver_id": receiver.pk,
                        "config_keys": list(config.keys()),
                    },
                )

                # Log the push
                self._structured_logger.log_crud_update(
                    receiver,
                    old_values={},
                    new_values=config,
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to push config to device: {e}",
                exc_info=True,
                extra={"receiver_id": receiver.pk},
            )
            return False

    # Helper methods

    def _map_device_type(self, model: str) -> str:
        """Map Shure model names to device_type choices."""
        model_upper = model.upper()
        if "ULXD4D" in model_upper or "ULXD4Q" in model_upper:
            return "ulxd"
        elif "QLXD" in model_upper:
            return "qlxd"
        elif "UHFR" in model_upper:
            return "uhfr"
        elif "AXT" in model_upper:
            return "axtd"
        else:
            return "ulxd"  # Default


# Register the service
from micboard.services.manufacturer_service import (
    ManufacturerServiceConfig,
    register_service,
)

register_service(
    ManufacturerServiceConfig(
        code="shure",
        name="Shure Incorporated",
        service_class=ShureService,
        enabled=True,
    )
)
