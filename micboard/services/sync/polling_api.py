"""Low-level API server polling service for device telemetry updates.

Handles direct polling of ManufacturerAPIServer instances and updates
local hardware/RF channel models. This is a low-level service focused on
API server health and device status synchronization.

For high-level manufacturer polling orchestration, use PollingService
from polling_service.py instead.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.integrations import ManufacturerAPIServer
from micboard.models.locations.structure import Location
from micboard.services.integrations.api_server_service import APIServerConnectionService


class APIServerPollingService:
    """Business logic for direct API server device status polling.

    This service handles low-level polling of manufacturer API servers.
    For high-level polling orchestration and broadcasting, see polling_service.py.
    """

    @staticmethod
    def poll_managed_device(
        *,
        server: ManufacturerAPIServer,
        chassis: WirelessChassis,
    ) -> int:
        """Poll one explicitly managed chassis through its persisted API server.

        The server's manufacturer and physical location form the ownership boundary.
        Validation happens before opening the vendor transport so a queued task cannot
        use one tenant's endpoint to update another tenant's hardware.
        """
        target_device_id = chassis.api_device_id.strip()
        if (
            not APIServerPollingService._server_owns_chassis(server, chassis)
            or not target_device_id
        ):
            raise PermissionDenied("API server does not own the requested managed chassis")

        if server.manufacturer != ManufacturerAPIServer.Manufacturer.SHURE:
            return 0

        try:
            api_devices = APIServerConnectionService.fetch_server_devices(server) or []
            target_devices = [
                device
                for device in api_devices
                if str(device.get("id") or device.get("api_device_id") or "").strip()
                == target_device_id
            ]

            from micboard.integrations.shure.plugin import ShurePlugin
            from micboard.services.sync.device_update_service import DeviceUpdateService

            updated = DeviceUpdateService.update_models_from_api_data(
                api_data=target_devices[:1],
                manufacturer=chassis.manufacturer,
                plugin=ShurePlugin(chassis.manufacturer),
            )

            server.status = ManufacturerAPIServer.Status.ACTIVE
            server.status_message = ""
            server.last_health_check = timezone.now()
            server.save(update_fields=["status", "status_message", "last_health_check"])
            return updated
        except Exception as exc:
            server.status = ManufacturerAPIServer.Status.ERROR
            server.status_message = f"Polling failed ({type(exc).__name__})"
            server.save(update_fields=["status", "status_message"])
            raise

    @staticmethod
    def _server_owns_chassis(
        server: ManufacturerAPIServer,
        chassis: WirelessChassis,
    ) -> bool:
        """Fail closed unless the server's legacy location name is globally unambiguous."""
        server_location = server.location_name.strip()
        if (
            not server.enabled
            or server.manufacturer != chassis.manufacturer.code
            or not server_location
            or chassis.location_id is None
        ):
            return False

        matching_location_ids = tuple(
            Location.objects.filter(name=server_location, is_active=True)
            .order_by("pk")
            .values_list("pk", flat=True)[:2]
        )
        return matching_location_ids == (chassis.location_id,)
