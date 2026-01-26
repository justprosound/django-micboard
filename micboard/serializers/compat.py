"""Compatibility serializer helpers expected by tests and older code.

These functions delegate to the DRF ModelSerializers defined in
`micboard.serializers.serializers` but provide the simple function API used
throughout the test suite.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from micboard.models import (
    Charger,
    DiscoveredDevice,
    Group,
    RFChannel,
    WirelessChassis,
    WirelessUnit,
)
from micboard.serializers.serializers import (
    ChannelSerializer,
    ChargerDetailSerializer,
    ChargerSummarySerializer,
    DeviceAssignmentSerializer,
    DiscoveredDeviceSerializer,
    GroupSerializer,
    ReceiverDetailSerializer,
    ReceiverSummarySerializer,
    TransmitterSerializer,
)

logger = logging.getLogger(__name__)


def _ensure_iterable(obj):
    if obj is None:
        return []
    if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        return obj
    return [obj]


def serialize_transmitter(unit: WirelessUnit, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a wireless unit as a transmitter payload."""
    data = TransmitterSerializer(unit).data
    if not include_extra:
        # remove extra computed fields
        for k in ("battery_health", "signal_quality", "is_active"):
            data.pop(k, None)
    return cast(dict[str, Any], data)


def serialize_channel(channel: RFChannel, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a channel with optional transmitter details."""
    data = ChannelSerializer(channel).data
    # If there is a wireless unit object but include_extra is False, remove
    # computed extra fields. If unit is None and include_extra is False,
    # remove the key entirely to match legacy serializer behaviour expected by tests.
    if "transmitter" in data:
        if data["transmitter"] is None and not include_extra:
            data.pop("transmitter", None)
        elif data["transmitter"] is not None and not include_extra:
            for k in ("battery_health", "signal_quality", "is_active"):
                data["transmitter"].pop(k, None)
    return cast(dict[str, Any], data)


def serialize_receiver(chassis: WirelessChassis, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a receiver, optionally including channels."""
    # Use detail serializer when include_extra True to include channels
    if include_extra:
        data = ReceiverDetailSerializer(chassis).data
    else:
        data = ReceiverSummarySerializer(chassis).data
    return cast(dict[str, Any], data)


def serialize_receiver_summary(chassis: WirelessChassis) -> dict[str, Any]:
    """Serialize a receiver summary without channel details."""
    return cast(dict[str, Any], ReceiverSummarySerializer(chassis).data)


def serialize_receiver_detail(chassis: WirelessChassis) -> dict[str, Any]:
    """Serialize a receiver with channel-level detail and clean null transmitters."""
    data = ReceiverDetailSerializer(chassis).data
    # Clean up channels: when a channel has no wireless unit, omit the key to match
    # legacy serialized shape expected by tests.
    channels = data.get("channels")
    if isinstance(channels, list):
        for ch in channels:
            if ch.get("transmitter") is None:
                ch.pop("transmitter", None)
    return cast(dict[str, Any], data)


def serialize_receivers(
    chassis_list: Iterable[WirelessChassis] | None = None,
    *,
    include_extra: bool = False,
    manufacturer_code: str | None = None,
) -> list[dict[str, Any]]:
    """Serialize a list of receivers with optional channel data."""
    if chassis_list is None:
        # Default behaviour: if a manufacturer_code is provided, return all
        # chassis for that manufacturer (including inactive). Otherwise
        # return only active chassis.
        if manufacturer_code:
            qs = WirelessChassis.objects.filter(manufacturer__code=manufacturer_code)
        else:
            qs = WirelessChassis.objects.filter(status="online")
        chassis_list = qs

    chassis_list = list(chassis_list)
    logger.debug("serialize_receivers: count=%d", len(chassis_list))
    if include_extra:
        out = []
        for chassis in chassis_list:
            try:
                d = ReceiverDetailSerializer(chassis).data
                # Clean channels as above
                channels = d.get("channels")
                if isinstance(channels, list):
                    for ch in channels:
                        if ch.get("transmitter") is None:
                            ch.pop("transmitter", None)
                out.append(d)
            except Exception as exc:
                logger.warning(
                    "serialize_receivers: failed to serialize chassis %s: %s",
                    getattr(chassis, "device_name", None),
                    exc,
                )
        logger.debug("serialize_receivers: returning %d items (include_extra)", len(out))
        return cast(list[dict[str, Any]], out)
    out = []
    for chassis in chassis_list:
        try:
            s = ReceiverSummarySerializer(chassis).data
            out.append(s)
            logger.debug(
                "serialize_receivers: serialized %s -> %s",
                chassis.device_name,
                s.get("api_device_id"),
            )
        except Exception as exc:
            logger.warning(
                "serialize_receivers: failed to summary-serialize %s: %s",
                getattr(chassis, "device_name", None),
                exc,
            )
    logger.debug("serialize_receivers: returning %d items (summary)", len(out))
    return cast(list[dict[str, Any]], out)


def serialize_discovered_device(device: DiscoveredDevice) -> dict[str, Any]:
    """Serialize a discovered device record."""
    return cast(dict[str, Any], DiscoveredDeviceSerializer(device).data)


def serialize_group(group: Group) -> dict[str, Any]:
    """Serialize a group reference."""
    return cast(dict[str, Any], GroupSerializer(group).data)


def serialize_charger(charger: Charger, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a charger with optional slot details."""
    # Use detail serializer when include_extra True to include slots
    if include_extra:
        data = ChargerDetailSerializer(charger).data
    else:
        data = ChargerSummarySerializer(charger).data
    return cast(dict[str, Any], data)


def serialize_charger_summary(charger: Charger) -> dict[str, Any]:
    """Serialize a charger summary payload."""
    return cast(dict[str, Any], ChargerSummarySerializer(charger).data)


def serialize_charger_detail(charger: Charger) -> dict[str, Any]:
    """Serialize a charger with slot details."""
    return cast(dict[str, Any], ChargerDetailSerializer(charger).data)


def serialize_chargers(
    chargers: Iterable[Charger] | None = None,
    *,
    include_extra: bool = False,
    manufacturer_code: str | None = None,
) -> list[dict[str, Any]]:
    """Serialize a list of chargers with optional slot details."""
    if chargers is None:
        # Default behaviour: if a manufacturer_code is provided, return all
        # chargers for that manufacturer (including inactive). Otherwise
        # return only active chargers.
        if manufacturer_code:
            qs = Charger.objects.filter(manufacturer__code=manufacturer_code)
        else:
            qs = Charger.objects.filter(is_active=True)
        chargers = qs

    chargers = list(chargers)
    if include_extra:
        return cast(list[dict[str, Any]], [ChargerDetailSerializer(c).data for c in chargers])
    return cast(list[dict[str, Any]], [ChargerSummarySerializer(c).data for c in chargers])


def serialize_assignment(assignment, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a single assignment."""
    return cast(dict[str, Any], DeviceAssignmentSerializer(assignment).data)


def serialize_assignments(assignments, include_extra: bool = False) -> list[dict[str, Any]]:
    """Serialize multiple assignments."""
    assignments = _ensure_iterable(assignments)
    return cast(list[dict[str, Any]], [DeviceAssignmentSerializer(a).data for a in assignments])


def serialize_location(location, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a single location."""
    # For now, return basic location data
    return {
        "id": location.id,
        "name": location.name,
        "description": location.description,
        "created_at": location.created_at,
        "updated_at": location.updated_at,
    }


def serialize_locations(locations, include_extra: bool = False) -> list[dict[str, Any]]:
    """Serialize multiple locations."""
    locations = _ensure_iterable(locations)
    return [serialize_location(loc, include_extra) for loc in locations]


def serialize_connection(connection, include_extra: bool = False) -> dict[str, Any]:
    """Serialize a single connection."""
    # For now, return basic connection data
    return {
        "id": connection.id,
        "manufacturer_code": connection.manufacturer_code,
        "connection_type": connection.connection_type,
        "status": connection.status,
        "connected_at": connection.connected_at,
        "last_heartbeat": connection.last_heartbeat,
        "error_count": connection.error_count,
        "created_at": connection.created_at,
    }


def serialize_connections(connections, include_extra: bool = False) -> list[dict[str, Any]]:
    """Serialize multiple connections."""
    connections = _ensure_iterable(connections)
    return [serialize_connection(conn, include_extra) for conn in connections]


__all__ = [
    "serialize_assignment",
    "serialize_assignments",
    "serialize_channel",
    "serialize_charger",
    "serialize_charger_detail",
    "serialize_charger_summary",
    "serialize_chargers",
    "serialize_connection",
    "serialize_connections",
    "serialize_discovered_device",
    "serialize_group",
    "serialize_location",
    "serialize_locations",
    "serialize_receiver",
    "serialize_receiver_detail",
    "serialize_receiver_summary",
    "serialize_receivers",
    "serialize_transmitter",
]
