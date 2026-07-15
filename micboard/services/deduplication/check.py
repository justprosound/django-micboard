from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.deduplication.identity_resolution import (
    resolve_mac_identity,
    resolve_serial_identity,
)
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
    serial_existing = resolve_serial_identity(serial_number, identity_index)
    mac_existing = resolve_mac_identity(mac_address, identity_index)
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

    return DeduplicationResult.new()


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
    return DeduplicationResult.conflict(
        conflict_type="durable_identity_mismatch",
        details={
            "serial_device_id": serial_existing.pk,
            "mac_device_id": mac_existing.pk,
        },
    )


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
            return DeduplicationResult.moved(
                existing,
                conflict_type="ip_changed",
                details={
                    "old_ip": existing.ip,
                    "new_ip": ip,
                    "match_type": "serial_number",
                },
            )

        return DeduplicationResult.duplicate(
            existing,
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
            return DeduplicationResult.moved(
                existing,
                conflict_type="ip_changed",
                details={
                    "old_ip": existing.ip,
                    "new_ip": ip,
                    "match_type": "mac_address",
                },
            )

        return DeduplicationResult.duplicate(
            existing,
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
    return DeduplicationResult.conflict(
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
            return DeduplicationResult.conflict(
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
            return DeduplicationResult.conflict(
                existing_device=existing,
                conflict_type="ip_conflict",
                details={
                    "existing_mac": existing.mac_address,
                    "new_mac": mac_address,
                    "match_type": "ip",
                },
            )

        return DeduplicationResult.duplicate(
            existing,
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
            return DeduplicationResult.moved(
                existing,
                conflict_type="ip_changed",
                details={
                    "old_ip": existing.ip,
                    "new_ip": ip,
                    "match_type": "api_device_id",
                },
            )

        return DeduplicationResult.duplicate(
            existing,
            details={"match_type": "api_device_id"},
        )

    return None
