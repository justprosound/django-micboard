"""Async versions of service methods for Django 4.2+/5.0+ async views.

Provides async wrappers for common service operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from micboard.services import (
    ConnectionHealthService,
    HardwareService,
    LocationService,
    ManufacturerService,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from micboard.models import Location, WirelessChassis, WirelessUnit


class AsyncHardwareService:
    """Async wrapper for HardwareService."""

    @staticmethod
    async def get_active_receivers() -> QuerySet:
        """Async: Get all active receivers."""
        return await sync_to_async(HardwareService.get_active_receivers)()

    @staticmethod
    async def get_online_receivers() -> QuerySet:
        """Async: Get all online receivers."""
        return await sync_to_async(HardwareService.get_online_receivers)()

    @staticmethod
    async def get_receiver_by_id(*, receiver_id: int) -> WirelessChassis:
        """Async: Get receiver by ID."""
        return await sync_to_async(HardwareService.get_receiver_by_id)(receiver_id=receiver_id)

    @staticmethod
    async def sync_device_status(*, device_obj, online: bool) -> None:
        """Async: Sync device online status."""
        return await sync_to_async(HardwareService.sync_device_status)(
            device_obj=device_obj, online=online
        )

    @staticmethod
    async def get_low_battery_receivers(*, threshold: int = 20) -> QuerySet:
        """Async: Get receivers with low battery."""
        return await sync_to_async(HardwareService.get_low_battery_receivers)(threshold=threshold)

    @staticmethod
    async def get_active_transmitters() -> QuerySet:
        """Async: Get all active transmitters."""
        return await sync_to_async(HardwareService.get_active_transmitters)()

    @staticmethod
    async def get_transmitter_by_id(*, transmitter_id: int) -> WirelessUnit:
        """Async: Get transmitter by ID."""
        return await sync_to_async(HardwareService.get_transmitter_by_id)(
            transmitter_id=transmitter_id
        )


class AsyncConnectionHealthService:
    """Async wrapper for ConnectionHealthService."""

    @staticmethod
    async def get_unhealthy_connections(*, heartbeat_timeout_seconds: int = 60) -> list:
        """Async: Get unhealthy connections."""
        return await sync_to_async(ConnectionHealthService.get_unhealthy_connections)(
            heartbeat_timeout_seconds=heartbeat_timeout_seconds
        )

    @staticmethod
    async def is_connection_healthy(*, connection_obj, heartbeat_timeout_seconds: int = 60) -> bool:
        """Async: Check if connection is healthy."""
        return await sync_to_async(ConnectionHealthService.is_connection_healthy)(
            connection_obj=connection_obj, heartbeat_timeout_seconds=heartbeat_timeout_seconds
        )

    @staticmethod
    async def update_heartbeat(*, connection_obj) -> None:
        """Async: Update connection heartbeat."""
        return await sync_to_async(ConnectionHealthService.update_heartbeat)(
            connection_obj=connection_obj
        )


class AsyncLocationService:
    """Async wrapper for LocationService."""

    @staticmethod
    async def create_location(*, name: str, description: str = "") -> Location:
        """Async: Create new location."""
        return await sync_to_async(LocationService.create_location)(
            name=name, description=description
        )

    @staticmethod
    async def list_all_locations() -> QuerySet:
        """Async: Get all locations."""
        return await sync_to_async(LocationService.list_all_locations)()

    @staticmethod
    async def assign_device_to_location(*, device_obj, location_obj: Location) -> None:
        """Async: Assign device to location."""
        return await sync_to_async(LocationService.assign_device_to_location)(
            device_obj=device_obj, location_obj=location_obj
        )


class AsyncManufacturerService:
    """Async wrapper for ManufacturerService."""

    @staticmethod
    async def sync_devices_for_manufacturer(*, manufacturer_code: str) -> dict:
        """Async: Sync devices for manufacturer."""
        return await sync_to_async(ManufacturerService.sync_devices_for_manufacturer)(
            manufacturer_code=manufacturer_code
        )

    @staticmethod
    async def get_manufacturer_config(*, manufacturer_code: str) -> dict:
        """Async: Get manufacturer configuration."""
        return await sync_to_async(ManufacturerService.get_manufacturer_config)(
            manufacturer_code=manufacturer_code
        )
