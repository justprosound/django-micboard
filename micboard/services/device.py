"""Device service layer for managing chassis and field units.

Handles device lifecycle operations, status synchronization, and queries.
Services operate independently from views and serializers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils import timezone

from micboard.models import WirelessChassis, WirelessUnit

if TYPE_CHECKING:
    pass


class DeviceService:
    """Business logic for device management and synchronization.

    Encapsulates operations on chassis, wireless units, and related device logic.

    Multi-tenancy support:
    Methods accept optional organization/site/campus parameters for filtering.
    When MSP or multi-site mode is disabled, these parameters are ignored.
    """

    @staticmethod
    def get_active_receivers(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet:
        """Fetch all active chassis (receivers/transmitters/transceivers).

        Args:
            organization_id: Optional organization ID (MSP mode).
            site_id: Optional site ID (multi-site mode).
            campus_id: Optional campus ID (MSP mode).

        Returns:
            QuerySet of active WirelessChassis objects.
        """
        from django.conf import settings

        qs = WirelessChassis.objects.active()

        # Apply tenant filtering if enabled
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            if organization_id:
                qs = qs.filter(location__building__organization_id=organization_id)
            if campus_id:
                qs = qs.filter(location__building__campus_id=campus_id)
        elif getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            if site_id:
                qs = qs.filter(location__building__site_id=site_id)

        return qs

    @staticmethod
    def get_active_transmitters(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet:
        """Fetch all active field units.

        Args:
            organization_id: Optional organization ID (MSP mode).
            site_id: Optional site ID (multi-site mode).
            campus_id: Optional campus ID (MSP mode).

        Returns:
            QuerySet of active WirelessUnit objects.
        """
        from django.conf import settings

        qs = WirelessUnit.objects.active()

        # Apply tenant filtering if enabled
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            if organization_id:
                qs = qs.filter(base_chassis__location__building__organization_id=organization_id)
            if campus_id:
                qs = qs.filter(base_chassis__location__building__campus_id=campus_id)
        elif getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            if site_id:
                qs = qs.filter(base_chassis__location__building__site_id=site_id)

        return qs

    @staticmethod
    def get_device_by_ip(*, ip_address: str) -> WirelessChassis | None:
        """Find a chassis by IP address.

        Args:
            ip_address: Device IP address.

        Returns:
            WirelessChassis object or None if not found.
        """
        return WirelessChassis.objects.filter(ip=ip_address).first()

    @staticmethod
    def get_receiver_by_id(*, receiver_id: int) -> WirelessChassis:
        """Get a chassis by its ID."""
        from micboard.services.exceptions import DeviceNotFoundError

        try:
            return WirelessChassis.objects.get(id=receiver_id)
        except WirelessChassis.DoesNotExist:
            raise DeviceNotFoundError(f"Chassis with ID {receiver_id} not found") from None

    @staticmethod
    def get_transmitter_by_id(*, transmitter_id: int) -> WirelessUnit:
        """Get a wireless unit by its ID."""
        from micboard.services.exceptions import DeviceNotFoundError

        try:
            return WirelessUnit.objects.get(id=transmitter_id)
        except WirelessUnit.DoesNotExist:
            raise DeviceNotFoundError(f"Wireless unit with ID {transmitter_id} not found") from None

    @staticmethod
    def sync_device_status(
        *,
        device_obj: WirelessChassis,
        online: bool,
    ) -> None:
        """Update chassis online status.

        Args:
            device_obj: WirelessChassis instance.
            online: Online status.
        """
        if device_obj.is_online != online:
            device_obj.is_online = online
            device_obj.status = "online" if online else "offline"
            device_obj.save(update_fields=["is_online", "status", "updated_at"])

    @staticmethod
    def sync_device_battery(
        *,
        device_obj: WirelessUnit,
        battery_level: int | None = None,
    ) -> None:
        """Update field unit battery level.

        Args:
            device_obj: WirelessUnit instance.
            battery_level: Battery level (0-255).
        """
        if battery_level is not None and device_obj.battery != battery_level:
            device_obj.battery = battery_level
            device_obj.save(update_fields=["battery", "updated_at"])

    @staticmethod
    def get_receivers_by_location(*, location_id: int) -> QuerySet:
        """Fetch all active chassis in a location.

        Args:
            location_id: Location primary key.

        Returns:
            QuerySet of WirelessChassis objects.
        """
        return WirelessChassis.objects.filter(location_id=location_id).active()

    @staticmethod
    def count_online_devices() -> dict[str, int]:
        """Get count of online devices by type.

        Returns:
            Dictionary with 'chassis' and 'units' counts.
        """
        return {
            "chassis": WirelessChassis.objects.filter(is_online=True).count(),
            "units": WirelessUnit.objects.filter(status="online").count(),
        }

    @staticmethod
    def create_or_update_receiver(
        *,
        manufacturer,
        location=None,
        device_id: str,
        name: str,
        is_online: bool = False,
        **kwargs,
    ) -> tuple[WirelessChassis, bool]:
        """Create or update a chassis device.

        Args:
            manufacturer: Manufacturer instance.
            location: Optional Location instance.
            device_id: Unique device identifier.
            name: Human-readable device name.
            is_online: Online status.
            **kwargs: Additional fields.

        Returns:
            Tuple of (chassis, created) where created is True if new.
        """
        if not device_id or not name:
            raise ValueError("device_id and name are required")

        chassis, created = WirelessChassis.objects.get_or_create(
            manufacturer=manufacturer,
            api_device_id=device_id,
            defaults={
                "name": name,
                "location": location,
                "is_online": is_online,
                "status": "online" if is_online else "discovered",
                **kwargs,
            },
        )

        if not created:
            # Update existing
            update_fields = []
            if chassis.name != name:
                chassis.name = name
                update_fields.append("name")
            if location and chassis.location != location:
                chassis.location = location
                update_fields.append("location")
            if chassis.is_online != is_online:
                chassis.is_online = is_online
                chassis.status = "online" if is_online else "offline"
                update_fields.extend(["is_online", "status"])

            if update_fields:
                chassis.save(update_fields=update_fields)

        return chassis, created

    @staticmethod
    def create_or_update_transmitter(
        *,
        manufacturer,
        chassis: WirelessChassis,
        slot: int,
        name: str,
        battery_level: int | None = None,
        **kwargs,
    ) -> tuple[WirelessUnit, bool]:
        """Create or update a wireless field unit.

        Args:
            manufacturer: Manufacturer instance.
            chassis: Base WirelessChassis instance.
            slot: Slot number on the chassis.
            name: Human-readable unit name.
            battery_level: Battery level (0-255).
            **kwargs: Additional fields.

        Returns:
            Tuple of (unit, created) where created is True if new.
        """
        if not name:
            raise ValueError("name is required")

        unit, created = WirelessUnit.objects.get_or_create(
            base_chassis=chassis,
            slot=slot,
            defaults={
                "name": name,
                "manufacturer": manufacturer,
                "battery": battery_level or 255,
                **kwargs,
            },
        )

        return unit, created

    @staticmethod
    def mark_device_offline(*, device_obj: WirelessChassis) -> None:
        """Mark a chassis as offline.

        Args:
            device_obj: WirelessChassis instance.
        """
        if device_obj.is_online:
            device_obj.is_online = False
            device_obj.status = "offline"
            device_obj.last_offline_at = timezone.now()
            device_obj.save(update_fields=["is_online", "status", "last_offline_at"])

    @staticmethod
    def mark_device_online(*, device_obj: WirelessChassis) -> None:
        """Mark a chassis as online.

        Args:
            device_obj: WirelessChassis instance.
        """
        if not device_obj.is_online:
            device_obj.is_online = True
            device_obj.status = "online"
            device_obj.last_online_at = timezone.now()
            device_obj.save(update_fields=["is_online", "status", "last_online_at"])

    @staticmethod
    def update_device_battery(
        *,
        device_obj: WirelessUnit,
        battery_level: int,
    ) -> None:
        """Update field unit battery level.

        Args:
            device_obj: WirelessUnit instance.
            battery_level: Battery level (0-255).
        """
        if not (0 <= battery_level <= 255):
            raise ValueError("battery_level must be 0-255")

        if device_obj.battery != battery_level:
            device_obj.battery = battery_level
            device_obj.save(update_fields=["battery"])

    @staticmethod
    def get_online_receivers() -> QuerySet:
        """Fetch all online chassis."""
        return WirelessChassis.objects.filter(is_online=True)

    @staticmethod
    def get_low_battery_receivers(*, threshold: int = 20) -> QuerySet:
        """Fetch chassis with at least one low battery unit."""
        return WirelessChassis.objects.filter(field_units__battery__lt=threshold).distinct()

    @staticmethod
    def get_low_battery_transmitters(*, threshold: int = 20) -> QuerySet:
        """Fetch units with low battery."""
        return WirelessUnit.objects.filter(battery__lt=threshold).exclude(battery=255)
