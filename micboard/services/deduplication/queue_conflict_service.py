"""Conflict classification for staged discovery queue entries."""

from __future__ import annotations

from micboard.models.discovery.discovery_queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.shared.base_dto import PydanticBaseDTO


class DiscoveryQueueConflict(PydanticBaseDTO):
    """Typed snapshot of one staged device's inventory conflicts."""

    is_duplicate: bool = False
    is_ip_conflict: bool = False
    existing_device: WirelessChassis | None = None
    existing_charger: Charger | None = None
    conflict_type: str | None = None

    @property
    def has_conflict(self) -> bool:
        """Return whether any durable identity or address is already owned."""
        return self.is_duplicate or self.is_ip_conflict


class DiscoveryQueueConflictService:
    """Classify staged device identity against adopted hardware inventory."""

    @staticmethod
    def check(entry: DiscoveryQueue) -> DiscoveryQueueConflict:
        """Return the strongest chassis or charger conflict for one queue entry."""
        if entry.serial_number:
            existing_chassis = WirelessChassis.objects.filter(
                serial_number=entry.serial_number
            ).first()
            if existing_chassis is not None:
                return DiscoveryQueueConflict(
                    is_duplicate=True,
                    existing_device=existing_chassis,
                    conflict_type=("moved" if existing_chassis.ip != entry.ip else "duplicate"),
                )

            existing_charger = Charger.objects.filter(serial_number=entry.serial_number).first()
            if existing_charger is not None:
                return DiscoveryQueueConflict(
                    is_duplicate=True,
                    existing_charger=existing_charger,
                    conflict_type=("moved" if existing_charger.ip != entry.ip else "duplicate"),
                )

        existing_chassis = WirelessChassis.objects.filter(ip=entry.ip).first()
        if existing_chassis is not None:
            return DiscoveryQueueConflict(
                is_ip_conflict=True,
                existing_device=existing_chassis,
                conflict_type=(
                    "ip_conflict"
                    if entry.serial_number and existing_chassis.serial_number != entry.serial_number
                    else "metadata_update"
                ),
            )

        existing_charger = Charger.objects.filter(ip=entry.ip).first()
        if existing_charger is not None:
            return DiscoveryQueueConflict(
                is_ip_conflict=True,
                existing_charger=existing_charger,
                conflict_type=(
                    "ip_conflict"
                    if entry.serial_number and existing_charger.serial_number != entry.serial_number
                    else "metadata_update"
                ),
            )

        return DiscoveryQueueConflict()
