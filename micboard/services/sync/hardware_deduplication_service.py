"""Device deduplication service for django-micboard.

Handles detection of duplicate devices, IP conflicts, and device movement
across the network. Provides authoritative device registry management.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from micboard.models import WirelessChassis

if TYPE_CHECKING:
    from micboard.models import (
        DeviceMovementLog,
        DiscoveryQueue,
        Manufacturer,
    )

logger = logging.getLogger(__name__)


class DeduplicationResult:
    """Result of device deduplication check."""

    def __init__(
        self,
        is_duplicate: bool = False,
        is_new: bool = False,
        is_moved: bool = False,
        is_conflict: bool = False,
        existing_device: WirelessChassis | None = None,
        conflict_type: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Store deduplication flags and related metadata."""
        self.is_duplicate = is_duplicate
        self.is_new = is_new
        self.is_moved = is_moved
        self.is_conflict = is_conflict
        self.existing_device = existing_device
        self.conflict_type = conflict_type
        self.details = details or {}

    def __repr__(self) -> str:
        """Return a concise textual representation for debugging."""
        if self.is_new:
            return "DeduplicationResult(new_device)"
        if self.is_moved:
            return f"DeduplicationResult(moved: {self.conflict_type})"
        if self.is_duplicate:
            return f"DeduplicationResult(duplicate: {self.conflict_type})"
        if self.is_conflict:
            return f"DeduplicationResult(conflict: {self.conflict_type})"
        return "DeduplicationResult(unknown)"


class HardwareDeduplicationService:
    """Service for managing device deduplication and conflict detection.

    Provides authoritative device registry by:
    1. Checking for duplicate serial numbers
    2. Detecting IP address conflicts
    3. Tracking device movements
    4. Validating device uniqueness
    """

    def __init__(self, manufacturer: Manufacturer | None = None):
        """Initialize deduplication service.

        Args:
            manufacturer: Optional manufacturer to scope checks
        """
        self.manufacturer = manufacturer

    def check_device(
        self,
        *,
        serial_number: str | None = None,
        mac_address: str | None = None,
        ip: str,
        api_device_id: str,
        manufacturer: Manufacturer | None = None,
    ) -> DeduplicationResult:
        """Check if a device is duplicate, moved, or conflicting.

        Args:
            serial_number: Device serial number (primary identity)
            mac_address: Device MAC address (hardware identity)
            ip: Current IP address
            api_device_id: Manufacturer API device ID
            manufacturer: Device manufacturer

        Returns:
            DeduplicationResult with conflict details
        """
        manufacturer = manufacturer or self.manufacturer
        if not manufacturer:
            raise ValueError("Manufacturer is required for deduplication")

        # Priority 1: Check by serial number (most reliable)
        if serial_number:
            result = self._check_by_serial(serial_number, ip, manufacturer)
            if result:
                return result

        # Priority 2: Check by MAC address (hardware identity)
        if mac_address:
            result = self._check_by_mac(mac_address, ip, manufacturer)
            if result:
                return result

        # Priority 3: Check by IP (detect IP conflicts)
        result = self._check_by_ip(ip, serial_number, mac_address, manufacturer)
        if result:
            return result

        # Priority 4: Check by API device ID (manufacturer-specific)
        result = self._check_by_api_id(api_device_id, ip, manufacturer)
        if result:
            return result

        # No conflicts found - this is a new device
        return DeduplicationResult(is_new=True)

    def _check_by_serial(
        self, serial_number: str, ip: str, manufacturer: Manufacturer
    ) -> DeduplicationResult | None:
        """Check for duplicate by serial number."""
        try:
            existing = WirelessChassis.objects.get(serial_number=serial_number)

            # Same device, check if it moved
            if existing.ip != ip:
                logger.info(
                    "Device %s moved: %s → %s",
                    serial_number,
                    existing.ip,
                    ip,
                )
                return DeduplicationResult(
                    is_moved=True,
                    existing_device=existing,
                    conflict_type="ip_changed",
                    details={
                        "old_ip": existing.ip,
                        "new_ip": ip,
                        "match_type": "serial_number",
                    },
                )

            # Same device, same IP - just an update
            if existing.manufacturer == manufacturer:
                return DeduplicationResult(
                    is_duplicate=True,
                    existing_device=existing,
                    conflict_type="duplicate",
                    details={"match_type": "serial_number"},
                )

            # Different manufacturer - suspicious!
            logger.warning(
                "Serial number %s exists for different manufacturer: %s vs %s",
                serial_number,
                existing.manufacturer.code,
                manufacturer.code,
            )
            return DeduplicationResult(
                is_conflict=True,
                existing_device=existing,
                conflict_type="manufacturer_mismatch",
                details={
                    "existing_manufacturer": existing.manufacturer.code,
                    "new_manufacturer": manufacturer.code,
                    "match_type": "serial_number",
                },
            )

        except WirelessChassis.DoesNotExist:
            pass

        return None

    def _check_by_mac(
        self, mac_address: str, ip: str, manufacturer: Manufacturer
    ) -> DeduplicationResult | None:
        """Check for duplicate by MAC address."""
        try:
            existing = WirelessChassis.objects.get(mac_address=mac_address)

            # Same hardware, check if IP changed
            if existing.ip != ip:
                logger.info(
                    "Device with MAC %s moved: %s → %s",
                    mac_address,
                    existing.ip,
                    ip,
                )
                return DeduplicationResult(
                    is_moved=True,
                    existing_device=existing,
                    conflict_type="ip_changed",
                    details={
                        "old_ip": existing.ip,
                        "new_ip": ip,
                        "match_type": "mac_address",
                    },
                )

            # Same device, same IP
            return DeduplicationResult(
                is_duplicate=True,
                existing_device=existing,
                conflict_type="duplicate",
                details={"match_type": "mac_address"},
            )

        except WirelessChassis.DoesNotExist:
            pass

        return None

    def _check_by_ip(
        self,
        ip: str,
        serial_number: str | None,
        mac_address: str | None,
        manufacturer: Manufacturer,
    ) -> DeduplicationResult | None:
        """Check for IP conflicts."""
        try:
            existing = WirelessChassis.objects.get(ip=ip)

            # Different serial number - IP conflict!
            if serial_number and existing.serial_number != serial_number:
                logger.warning(
                    "IP conflict at %s: %s vs %s",
                    ip,
                    existing.serial_number,
                    serial_number,
                )
                return DeduplicationResult(
                    is_conflict=True,
                    existing_device=existing,
                    conflict_type="ip_conflict",
                    details={
                        "existing_serial": existing.serial_number,
                        "new_serial": serial_number,
                        "existing_mac": existing.mac_address,
                        "new_mac": mac_address,
                        "match_type": "ip",
                    },
                )

            # Different MAC address - IP conflict!
            if mac_address and existing.mac_address != mac_address:
                logger.warning(
                    "IP conflict at %s: MAC %s vs %s",
                    ip,
                    existing.mac_address,
                    mac_address,
                )
                return DeduplicationResult(
                    is_conflict=True,
                    existing_device=existing,
                    conflict_type="ip_conflict",
                    details={
                        "existing_mac": existing.mac_address,
                        "new_mac": mac_address,
                        "match_type": "ip",
                    },
                )

            # Same device at same IP
            return DeduplicationResult(
                is_duplicate=True,
                existing_device=existing,
                conflict_type="duplicate",
                details={"match_type": "ip"},
            )

        except WirelessChassis.DoesNotExist:
            pass

        return None

    def _check_by_api_id(
        self, api_device_id: str, ip: str, manufacturer: Manufacturer
    ) -> DeduplicationResult | None:
        """Check by manufacturer's API device ID."""
        try:
            existing = WirelessChassis.objects.get(
                manufacturer=manufacturer,
                api_device_id=api_device_id,
            )

            # Same device in manufacturer's system
            if existing.ip != ip:
                logger.info(
                    "Device %s moved: %s → %s",
                    api_device_id,
                    existing.ip,
                    ip,
                )
                return DeduplicationResult(
                    is_moved=True,
                    existing_device=existing,
                    conflict_type="ip_changed",
                    details={
                        "old_ip": existing.ip,
                        "new_ip": ip,
                        "match_type": "api_device_id",
                    },
                )

            # Same device, same IP
            return DeduplicationResult(
                is_duplicate=True,
                existing_device=existing,
                conflict_type="duplicate",
                details={"match_type": "api_device_id"},
            )

        except WirelessChassis.DoesNotExist:
            pass

        return None

    def find_duplicate(
        self, api_data: dict[str, Any], manufacturer: Manufacturer
    ) -> WirelessChassis | None:
        """Find an existing device that matches the API data."""
        serial = api_data.get("serial_number") or api_data.get("serialNumber")
        mac = api_data.get("mac_address") or api_data.get("macAddress")
        api_id = api_data.get("id") or api_data.get("api_device_id")
        ip = api_data.get("ip") or api_data.get("ipAddress")

        if serial:
            chassis = WirelessChassis.objects.filter(serial_number=serial).first()
            if chassis:
                return chassis

        if mac:
            chassis = WirelessChassis.objects.filter(mac_address=mac).first()
            if chassis:
                return chassis

        if api_id:
            chassis = WirelessChassis.objects.filter(
                manufacturer=manufacturer, api_device_id=api_id
            ).first()
            if chassis:
                return chassis

        if ip:
            chassis = WirelessChassis.objects.filter(ip=ip).first()
            if chassis:
                return chassis

        return None

    @transaction.atomic
    def log_device_movement(
        self,
        device: WirelessChassis,
        old_ip: str | None = None,
        new_ip: str | None = None,
        old_location=None,
        new_location=None,
        detected_by: str = "auto",
        reason: str = "",
    ) -> DeviceMovementLog:
        """Log device movement (IP or location change).

        Args:
            device: Device that moved
            old_ip: Previous IP address
            new_ip: New IP address
            old_location: Previous location
            new_location: New location
            detected_by: How movement was detected
            reason: Movement reason/notes

        Returns:
            DeviceMovementLog instance
        """
        from micboard.models import DeviceMovementLog

        movement = DeviceMovementLog.objects.create(
            device=device,
            old_ip=old_ip,
            new_ip=new_ip,
            old_location=old_location,
            new_location=new_location,
            detected_by=detected_by,
            reason=reason,
        )

        logger.info(
            "Logged movement for %s: %s",
            device.name or device.api_device_id,
            movement.movement_type,
        )

        return movement

    @transaction.atomic
    def queue_for_approval(
        self,
        *,
        manufacturer: Manufacturer,
        api_data: dict[str, Any],
        dedup_result: DeduplicationResult,
    ) -> DiscoveryQueue:
        """Add discovered device to approval queue.

        Args:
            manufacturer: Device manufacturer
            api_data: Raw API device data
            dedup_result: Deduplication check result

        Returns:
            DiscoveryQueue instance
        """
        from micboard.models import DiscoveryQueue

        # Extract key fields from API data
        serial_number = api_data.get("serial_number") or api_data.get("serialNumber") or ""
        api_device_id = api_data.get("id") or api_data.get("api_device_id") or ""
        ip = api_data.get("ip") or api_data.get("ipAddress") or ""
        device_type = api_data.get("device_type") or api_data.get("model") or "unknown"
        name = api_data.get("name") or ""
        firmware = api_data.get("firmware_version") or api_data.get("firmware") or ""

        # Determine status based on deduplication result
        if dedup_result.is_conflict:
            status = "pending"  # Requires admin review
        elif dedup_result.is_duplicate:
            status = "duplicate"
        else:
            status = "pending"

        # Create queue entry
        queue_entry = DiscoveryQueue.objects.create(
            manufacturer=manufacturer,
            serial_number=serial_number,
            api_device_id=api_device_id,
            ip=ip,
            device_type=device_type,
            name=name,
            firmware_version=firmware,
            metadata=api_data,
            status=status,
            existing_device=dedup_result.existing_device,
            is_duplicate=dedup_result.is_duplicate or dedup_result.is_moved,
            is_ip_conflict=dedup_result.is_conflict,
        )

        logger.info(
            "Queued device for approval: %s (%s) - Status: %s",
            name or api_device_id,
            serial_number or ip,
            status,
        )

        return queue_entry

    def get_unacknowledged_movements(
        self, manufacturer: Manufacturer | None = None
    ) -> list[DeviceMovementLog]:
        """Get list of unacknowledged device movements."""
        from micboard.models import DeviceMovementLog

        qs = DeviceMovementLog.objects.filter(acknowledged=False)

        if manufacturer:
            qs = qs.filter(device__manufacturer=manufacturer)

        return list(qs.select_related("device", "old_location", "new_location"))

    def get_pending_approvals(
        self, manufacturer: Manufacturer | None = None
    ) -> list[DiscoveryQueue]:
        """Get list of devices pending approval."""
        from micboard.models import DiscoveryQueue

        qs = DiscoveryQueue.objects.filter(status="pending")

        if manufacturer:
            qs = qs.filter(manufacturer=manufacturer)

        return list(qs.select_related("manufacturer", "existing_device"))

    def check_api_id_conflicts(
        self, api_device_id: str, manufacturer: Manufacturer
    ) -> tuple[int, list]:
        """Check for duplicate API device IDs within same manufacturer.

        API device IDs should be unique per manufacturer. If multiple
        chassis share the same API device ID, it indicates:
        - API bug (duplicate ID generation)
        - Network loop (device registered multiple times)
        - Firmware issue (device not properly identified)

        Args:
            api_device_id: Manufacturer's device identifier
            manufacturer: Manufacturer instance

        Returns:
            Tuple of (count, list of WirelessChassis IDs with duplicate API ID)
        """
        duplicates = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            api_device_id=api_device_id,
        ).values_list("id", "name", "ip", "serial_number")

        if len(duplicates) > 1:
            logger.warning(
                "🚨 API ID DUPLICATE DETECTED: %s:%s exists in %d receivers: %s",
                manufacturer.code,
                api_device_id,
                len(duplicates),
                [f"{name}@{ip}" for _, name, ip, _ in duplicates],
            )

        return len(duplicates), list(duplicates)

    def check_cross_vendor_api_id(self, api_device_id: str) -> list[tuple[str, int, list]]:
        """Check if API device ID exists in other manufacturers.

        Args:
            api_device_id: Device identifier to check

        Returns:
            List of tuples (manufacturer_code, count, devices)
        """
        from micboard.models import Manufacturer

        results = []
        for mfg in Manufacturer.objects.filter(is_active=True).exclude(
            id=self.manufacturer.id if self.manufacturer else -1
        ):
            duplicates_qs = WirelessChassis.objects.filter(
                manufacturer=mfg,
                api_device_id=api_device_id,
            )
            cross_vendor_count = duplicates_qs.count()

            if cross_vendor_count > 0:
                logger.warning(
                    "⚠️  CROSS-VENDOR API ID: %s also exists in %s (%d devices)",
                    api_device_id,
                    mfg.code,
                    cross_vendor_count,
                )
                results.append((mfg.code, cross_vendor_count, list(duplicates_qs)))

        return results


def get_hardware_deduplication_service(
    manufacturer: Manufacturer | None = None,
) -> HardwareDeduplicationService:
    """Get deduplication service instance."""
    return HardwareDeduplicationService(manufacturer)
