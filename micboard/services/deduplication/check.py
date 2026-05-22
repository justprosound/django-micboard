from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.models import WirelessChassis
from micboard.services.deduplication.result import DeduplicationResult

if TYPE_CHECKING:
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


def check_device(
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
    if not manufacturer:
        raise ValueError("Manufacturer is required for deduplication")

    if serial_number:
        result = _check_by_serial(serial_number, ip, manufacturer)
        if result:
            return result

    if mac_address:
        result = _check_by_mac(mac_address, ip, manufacturer)
        if result:
            return result

    result = _check_by_ip(ip, serial_number, mac_address, manufacturer)
    if result:
        return result

    result = _check_by_api_id(api_device_id, ip, manufacturer)
    if result:
        return result

    return DeduplicationResult(is_new=True)


def find_duplicate(api_data: dict[str, Any], manufacturer: Manufacturer) -> WirelessChassis | None:
    """Find an existing device matching the API data."""
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


def check_api_id_conflicts(api_device_id: str, manufacturer: Manufacturer) -> tuple[int, list]:
    """Check for duplicate API device IDs within same manufacturer."""
    duplicates = WirelessChassis.objects.filter(
        manufacturer=manufacturer,
        api_device_id=api_device_id,
    ).values_list("id", "name", "ip", "serial_number")

    if len(duplicates) > 1:
        logger.warning(
            "API ID DUPLICATE: %s:%s in %d receivers: %s",
            manufacturer.code,
            api_device_id,
            len(duplicates),
            [f"{name}@{ip}" for _, name, ip, _ in duplicates],
        )

    return len(duplicates), list(duplicates)


def check_cross_vendor_api_id(
    api_device_id: str, current_manufacturer: Manufacturer | None = None
) -> list[tuple[str, int, list]]:
    """Check if API device ID exists in other manufacturers.

    Args:
        api_device_id: Device identifier to check
        current_manufacturer: Manufacturer to exclude from the check

    Returns:
        List of tuples (manufacturer_code, count, devices)
    """
    from micboard.models import Manufacturer

    results: list[tuple[str, int, list]] = []
    exclude_id = current_manufacturer.id if current_manufacturer else -1

    for mfg in Manufacturer.objects.filter(is_active=True).exclude(id=exclude_id):
        duplicates_qs = WirelessChassis.objects.filter(
            manufacturer=mfg,
            api_device_id=api_device_id,
        )
        cross_vendor_count = duplicates_qs.count()

        if cross_vendor_count > 0:
            logger.warning(
                "CROSS-VENDOR API ID: %s also in %s (%d devices)",
                api_device_id,
                mfg.code,
                cross_vendor_count,
            )
            results.append((mfg.code, cross_vendor_count, list(duplicates_qs)))

    return results


def _check_by_serial(
    serial_number: str, ip: str, manufacturer: Manufacturer
) -> DeduplicationResult | None:
    """Check for duplicate by serial number."""
    try:
        existing = WirelessChassis.objects.get(serial_number=serial_number)

        if existing.ip != ip:
            logger.info(
                "Device %s moved: %s -> %s",
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

        if existing.manufacturer == manufacturer:
            return DeduplicationResult(
                is_duplicate=True,
                existing_device=existing,
                conflict_type="duplicate",
                details={"match_type": "serial_number"},
            )

        logger.warning(
            "Serial %s exists for different mfg: %s vs %s",
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
    mac_address: str, ip: str, manufacturer: Manufacturer
) -> DeduplicationResult | None:
    """Check for duplicate by MAC address."""
    try:
        existing = WirelessChassis.objects.get(mac_address=mac_address)

        if existing.ip != ip:
            logger.info(
                "Device with MAC %s moved: %s -> %s",
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
    ip: str,
    serial_number: str | None,
    mac_address: str | None,
    manufacturer: Manufacturer,
) -> DeduplicationResult | None:
    """Check for IP conflicts."""
    try:
        existing = WirelessChassis.objects.get(ip=ip)

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
    api_device_id: str, ip: str, manufacturer: Manufacturer
) -> DeduplicationResult | None:
    """Check by manufacturer's API device ID."""
    try:
        existing = WirelessChassis.objects.get(
            manufacturer=manufacturer,
            api_device_id=api_device_id,
        )

        if existing.ip != ip:
            logger.info(
                "Device %s moved: %s -> %s",
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

        return DeduplicationResult(
            is_duplicate=True,
            existing_device=existing,
            conflict_type="duplicate",
            details={"match_type": "api_device_id"},
        )

    except WirelessChassis.DoesNotExist:
        pass

    return None
