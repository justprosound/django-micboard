"""What the identity index says about a normalized chassis payload."""

from typing import TYPE_CHECKING

from micboard.services.core.hardware import NormalizedChassis
from micboard.services.deduplication.identity_index import DeviceIdentityIndex

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer


def named_chassis_ids(
    payload: NormalizedChassis,
    manufacturer: Manufacturer,
    identity_index: DeviceIdentityIndex,
) -> frozenset[int]:
    """Return the chassis of this manufacturer that any identity of the payload names."""
    candidates = (
        identity_index.serial(payload.serial_number) if payload.serial_number else None,
        identity_index.mac(payload.mac_address) if payload.mac_address else None,
        identity_index.ip(payload.ip) if payload.ip else None,
        identity_index.api_id(manufacturer.pk, payload.api_device_id),
    )
    return frozenset(
        chassis.pk
        for chassis in candidates
        if chassis is not None and chassis.manufacturer_id == manufacturer.pk
    )


def with_known_address(
    payload: NormalizedChassis,
    manufacturer: Manufacturer,
    identity_index: DeviceIdentityIndex,
) -> NormalizedChassis:
    """Give an address-less event the address of the chassis its API id already names."""
    if payload.ip:
        return payload
    known = identity_index.api_id(manufacturer.pk, payload.api_device_id)
    if known is None:
        return payload
    # An address that belongs to the API id's chassis is not this payload's when its serial
    # or MAC names another chassis: that is an identity conflict, not a missing address.
    others = (
        identity_index.serial(payload.serial_number) if payload.serial_number else None,
        identity_index.mac(payload.mac_address) if payload.mac_address else None,
    )
    if any(other is not None and other.pk != known.pk for other in others):
        return payload
    return payload.model_copy(update={"ip": str(known.ip)})
