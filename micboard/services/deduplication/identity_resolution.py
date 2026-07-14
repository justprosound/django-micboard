"""Durable device-identity lookup helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.utils.mac_address import mac_address_query_variants

if TYPE_CHECKING:
    from micboard.services.deduplication.identity_index import DeviceIdentityIndex


def resolve_serial_identity(
    serial_number: str | None,
    identity_index: DeviceIdentityIndex | None,
) -> WirelessChassis | None:
    """Resolve a supplied serial once across indexed and query paths."""
    if not serial_number:
        return None
    if identity_index is not None:
        return identity_index.serial(serial_number)
    try:
        return WirelessChassis.objects.get(serial_number=serial_number)
    except WirelessChassis.DoesNotExist:
        return None


def resolve_mac_identity(
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
