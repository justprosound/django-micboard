from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.deduplication.result import DeduplicationResult
from micboard.utils.mac_address import canonicalize_mac_address, mac_address_query_variants

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.services.deduplication.identity_index import DeviceIdentityIndex

logger = logging.getLogger(__name__)


def check_device(
    *,
    serial_number: str | None = None,
    mac_address: str | None = None,
    ip: str,
    api_device_id: str,
    manufacturer: Manufacturer | None = None,
    identity_index: DeviceIdentityIndex | None = None,
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

    mac_address = canonicalize_mac_address(mac_address)
    serial_existing = _resolve_serial_identity(serial_number, identity_index)
    mac_existing = _resolve_mac_identity(mac_address, identity_index)
    if durable_conflict := _check_durable_identity_conflict(
        serial_existing=serial_existing,
        mac_existing=mac_existing,
        manufacturer=manufacturer,
    ):
        return durable_conflict

    if serial_number:
        result = _check_by_serial(
            serial_number,
            ip,
            manufacturer,
            existing=serial_existing,
            indexed=True,
        )
        if result:
            return result

    if mac_address:
        result = _check_by_mac(
            mac_address,
            ip,
            manufacturer,
            existing=mac_existing,
            indexed=True,
        )
        if result:
            return result

    result = _check_by_ip(
        ip,
        serial_number,
        mac_address,
        manufacturer,
        existing=identity_index.ip(ip) if identity_index else None,
        indexed=identity_index is not None,
    )
    if result:
        return result

    result = _check_by_api_id(
        api_device_id,
        ip,
        manufacturer,
        existing=(
            identity_index.api_id(manufacturer.pk, api_device_id) if identity_index else None
        ),
        indexed=identity_index is not None,
    )
    if result:
        return result

    return DeduplicationResult(is_new=True)


def _resolve_serial_identity(
    serial_number: str | None,
    identity_index: DeviceIdentityIndex | None,
) -> WirelessChassis | None:
    """Resolve a supplied serial once so every durable identity can be validated."""
    if not serial_number:
        return None
    if identity_index is not None:
        return identity_index.serial(serial_number)
    try:
        return WirelessChassis.objects.get(serial_number=serial_number)
    except WirelessChassis.DoesNotExist:
        return None


def _resolve_mac_identity(
    mac_address: str | None,
    identity_index: DeviceIdentityIndex | None,
) -> WirelessChassis | None:
    """Resolve a supplied canonical MAC once across indexed and query paths."""
    if not mac_address:
        return None
    if identity_index is not None:
        return identity_index.mac(mac_address)
    try:
        return WirelessChassis.objects.get(mac_address__in=mac_address_query_variants(mac_address))
    except WirelessChassis.DoesNotExist:
        return None


def _check_durable_identity_conflict(
    *,
    serial_existing: WirelessChassis | None,
    mac_existing: WirelessChassis | None,
    manufacturer: Manufacturer,
) -> DeduplicationResult | None:
    """Reject foreign ownership or two durable keys that resolve to different rows."""
    for existing, match_type in (
        (serial_existing, "serial_number"),
        (mac_existing, "mac_address"),
    ):
        if existing is None:
            continue
        if conflict := _check_manufacturer_conflict(
            existing,
            manufacturer,
            match_type=match_type,
        ):
            return conflict

    if serial_existing is None or mac_existing is None or serial_existing.pk == mac_existing.pk:
        return None

    logger.warning(
        "Device identity conflict during deduplication "
        "(manufacturer=%s, conflict=durable_identity_mismatch, "
        "serial_device_id=%s, mac_device_id=%s)",
        manufacturer.code,
        serial_existing.pk,
        mac_existing.pk,
    )
    return DeduplicationResult(
        is_conflict=True,
        conflict_type="durable_identity_mismatch",
        details={
            "serial_device_id": serial_existing.pk,
            "mac_device_id": mac_existing.pk,
        },
    )


def find_duplicate(api_data: dict[str, Any], manufacturer: Manufacturer) -> WirelessChassis | None:
    """Find an existing device matching the API data."""
    serial = api_data.get("serial_number") or api_data.get("serialNumber")
    mac = canonicalize_mac_address(api_data.get("mac_address") or api_data.get("macAddress"))
    api_id = api_data.get("id") or api_data.get("api_device_id")
    ip = api_data.get("ip") or api_data.get("ipAddress")

    if serial:
        chassis = WirelessChassis.objects.filter(serial_number=serial).first()
        if chassis:
            return chassis

    if mac:
        chassis = WirelessChassis.objects.filter(
            mac_address__in=mac_address_query_variants(mac)
        ).first()
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
            "Duplicate manufacturer API identity detected "
            "(manufacturer=%s, conflict=api_device_id, count=%d, device_ids=%s)",
            manufacturer.code,
            len(duplicates),
            [device_id for device_id, *_ in duplicates],
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
    from micboard.models.discovery.manufacturer import Manufacturer

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
                "Cross-vendor API identity detected "
                "(manufacturer=%s, conflict=cross_vendor_api_device_id, count=%d)",
                mfg.code,
                cross_vendor_count,
            )
            results.append((mfg.code, cross_vendor_count, list(duplicates_qs)))

    return results


def _check_by_serial(
    serial_number: str,
    ip: str,
    manufacturer: Manufacturer,
    *,
    existing: WirelessChassis | None = None,
    indexed: bool = False,
) -> DeduplicationResult | None:
    """Check for duplicate by serial number."""
    if not indexed:
        try:
            existing = WirelessChassis.objects.get(serial_number=serial_number)
        except WirelessChassis.DoesNotExist:
            return None

    if existing is not None:
        manufacturer_conflict = _check_manufacturer_conflict(
            existing,
            manufacturer,
            match_type="serial_number",
        )
        if manufacturer_conflict is not None:
            return manufacturer_conflict

        if existing.ip != ip:
            logger.info(
                "Device moved after deduplication match "
                "(device_id=%s, manufacturer=%s, match_type=serial_number)",
                existing.pk,
                manufacturer.code,
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

        return DeduplicationResult(
            is_duplicate=True,
            existing_device=existing,
            conflict_type="duplicate",
            details={"match_type": "serial_number"},
        )

    return None


def _check_by_mac(
    mac_address: str,
    ip: str,
    manufacturer: Manufacturer,
    *,
    existing: WirelessChassis | None = None,
    indexed: bool = False,
) -> DeduplicationResult | None:
    """Check for duplicate by MAC address."""
    canonical_mac_address = canonicalize_mac_address(mac_address)
    if canonical_mac_address is None:
        return None
    mac_address = canonical_mac_address
    if not indexed:
        try:
            existing = WirelessChassis.objects.get(
                mac_address__in=mac_address_query_variants(mac_address)
            )
        except WirelessChassis.DoesNotExist:
            return None

    if existing is not None:
        manufacturer_conflict = _check_manufacturer_conflict(
            existing,
            manufacturer,
            match_type="mac_address",
        )
        if manufacturer_conflict is not None:
            return manufacturer_conflict

        if existing.ip != ip:
            logger.info(
                "Device moved after deduplication match "
                "(device_id=%s, manufacturer=%s, match_type=mac_address)",
                existing.pk,
                manufacturer.code,
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

    return None


def _check_manufacturer_conflict(
    existing: WirelessChassis,
    manufacturer: Manufacturer,
    *,
    match_type: str,
) -> DeduplicationResult | None:
    """Reject a hardware identity owned by another manufacturer."""
    if existing.manufacturer_id == manufacturer.pk:
        return None

    logger.warning(
        "Device identity conflict during deduplication "
        "(device_id=%s, existing_manufacturer=%s, new_manufacturer=%s, "
        "match_type=%s, conflict=manufacturer_mismatch)",
        existing.pk,
        existing.manufacturer.code,
        manufacturer.code,
        match_type,
    )
    return DeduplicationResult(
        is_conflict=True,
        existing_device=existing,
        conflict_type="manufacturer_mismatch",
        details={
            "existing_manufacturer": existing.manufacturer.code,
            "new_manufacturer": manufacturer.code,
            "match_type": match_type,
        },
    )


def _check_by_ip(
    ip: str,
    serial_number: str | None,
    mac_address: str | None,
    manufacturer: Manufacturer,
    *,
    existing: WirelessChassis | None = None,
    indexed: bool = False,
) -> DeduplicationResult | None:
    """Check for IP conflicts."""
    if not indexed:
        try:
            existing = WirelessChassis.objects.get(ip=ip)
        except WirelessChassis.DoesNotExist:
            return None

    if existing is not None:
        if serial_number and existing.serial_number != serial_number:
            logger.warning(
                "Device identity conflict during deduplication "
                "(device_id=%s, manufacturer=%s, match_type=ip, identity=serial_number)",
                existing.pk,
                manufacturer.code,
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

        if mac_address and canonicalize_mac_address(existing.mac_address) != mac_address:
            logger.warning(
                "Device identity conflict during deduplication "
                "(device_id=%s, manufacturer=%s, match_type=ip, identity=mac_address)",
                existing.pk,
                manufacturer.code,
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

    return None


def _check_by_api_id(
    api_device_id: str,
    ip: str,
    manufacturer: Manufacturer,
    *,
    existing: WirelessChassis | None = None,
    indexed: bool = False,
) -> DeduplicationResult | None:
    """Check by manufacturer's API device ID."""
    if not indexed:
        try:
            existing = WirelessChassis.objects.get(
                manufacturer=manufacturer,
                api_device_id=api_device_id,
            )
        except WirelessChassis.DoesNotExist:
            return None

    if existing is not None:
        if existing.ip != ip:
            logger.info(
                "Device moved after deduplication match "
                "(device_id=%s, manufacturer=%s, match_type=api_device_id)",
                existing.pk,
                manufacturer.code,
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

    return None
