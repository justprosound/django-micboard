"""
Serializers for django-micboard models.

This module provides reusable serialization functions for converting
Django model instances to dictionaries suitable for JSON responses.
Centralizing serialization logic ensures consistency and follows DRY principles.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models import Channel, DiscoveredDevice, Group, Receiver, Transmitter


def serialize_transmitter(transmitter: Transmitter, *, include_extra: bool = False) -> dict[str, Any]:
    """
    Serialize a Transmitter instance to a dictionary.

    Args:
        transmitter: The Transmitter instance to serialize
        include_extra: If True, includes computed properties like battery_health,
                      signal_quality, and is_active (keyword-only)

    Returns:
        Dictionary representation of the transmitter
    """
    data = {
        "slot": transmitter.slot,
        "battery": transmitter.battery,
        "battery_charge": transmitter.battery_charge,
        "battery_percentage": transmitter.battery_percentage,
        "audio_level": transmitter.audio_level,
        "rf_level": transmitter.rf_level,
        "frequency": transmitter.frequency,
        "antenna": transmitter.antenna,
        "tx_offset": transmitter.tx_offset,
        "quality": transmitter.quality,
        "runtime": transmitter.runtime,
        "status": transmitter.status,
        "name": transmitter.name,
        "name_raw": transmitter.name_raw,
        "updated_at": transmitter.updated_at.isoformat(),
    }

    if include_extra:
        data.update(
            {
                "battery_health": transmitter.battery_health,
                "signal_quality": transmitter.get_signal_quality(),
                "is_active": transmitter.is_active,
            }
        )

    return data


def serialize_channel(channel: Channel, *, include_extra: bool = False) -> dict[str, Any]:
    """
    Serialize a Channel instance to a dictionary.

    Args:
        channel: The Channel instance to serialize
        include_extra: If True, includes extra transmitter details (keyword-only)

    Returns:
        Dictionary representation of the channel
    """
    data = {
        "channel_number": channel.channel_number,
    }

    if hasattr(channel, "transmitter"):
        data["transmitter"] = serialize_transmitter(channel.transmitter, include_extra=include_extra)

    return data


def serialize_receiver(receiver: Receiver, *, include_extra: bool = False) -> dict[str, Any]:
    """
    Serialize a Receiver instance to a dictionary.

    Args:
        receiver: The Receiver instance to serialize
        include_extra: If True, includes health_status and other computed properties (keyword-only)

    Returns:
        Dictionary representation of the receiver with channels and transmitters
    """
    data = {
        "api_device_id": receiver.api_device_id,
        "ip": receiver.ip,
        "type": receiver.device_type,
        "name": receiver.name,
        "firmware": receiver.firmware_version,
        "is_active": receiver.is_active,
        "last_seen": receiver.last_seen.isoformat() if receiver.last_seen else None,
        "channels": [],
    }

    if include_extra:
        data["health_status"] = receiver.health_status

    for channel in receiver.channels.all():
        data["channels"].append(serialize_channel(channel, include_extra=include_extra))

    return data


def serialize_receivers(
    receivers: list[Receiver] | None = None, *, include_extra: bool = False
) -> list[dict[str, Any]]:
    """
    Serialize multiple Receiver instances.

    Args:
        receivers: List of Receiver instances. If None, fetches all active receivers.
        include_extra: If True, includes extra computed properties (keyword-only)

    Returns:
        List of serialized receiver dictionaries
    """
    # Import here to avoid circular imports
    from micboard.models import Receiver

    if receivers is None:
        receivers = list(
            Receiver.objects.filter(is_active=True).prefetch_related("channels__transmitter")
        )

    return [serialize_receiver(receiver, include_extra=include_extra) for receiver in receivers]


def serialize_discovered_device(device: DiscoveredDevice) -> dict[str, Any]:
    """
    Serialize a DiscoveredDevice instance to a dictionary.

    Args:
        device: The DiscoveredDevice instance to serialize

    Returns:
        Dictionary representation of the discovered device
    """
    return {
        "ip": device.ip,
        "type": device.device_type,
        "channels": device.channels,
        "discovered_at": device.discovered_at.isoformat() if device.discovered_at else None,
    }


def serialize_group(group: Group) -> dict[str, Any]:
    """
    Serialize a Group instance to a dictionary.

    Args:
        group: The Group instance to serialize

    Returns:
        Dictionary representation of the group
    """
    return {
        "group": group.group_number,
        "title": group.title,
        "slots": group.slots,
        "hide_charts": group.hide_charts,
    }


def serialize_receiver_summary(receiver: Receiver) -> dict[str, Any]:
    """
    Serialize a Receiver instance to a summary dictionary (without channels).

    Useful for list views where full channel/transmitter details aren't needed.

    Args:
        receiver: The Receiver instance to serialize

    Returns:
        Dictionary with receiver summary information
    """
    return {
        "api_device_id": receiver.api_device_id,
        "name": receiver.name,
        "device_type": receiver.device_type,
        "ip": receiver.ip,
        "is_active": receiver.is_active,
        "health_status": receiver.health_status,
        "last_seen": receiver.last_seen.isoformat() if receiver.last_seen else None,
        "channel_count": receiver.get_channel_count(),
    }


def serialize_receiver_detail(receiver: Receiver) -> dict[str, Any]:
    """
    Serialize a Receiver instance with full details including channels and transmitters.

    Args:
        receiver: The Receiver instance to serialize

    Returns:
        Dictionary with complete receiver, channel, and transmitter information
    """
    channels = []
    for channel in receiver.channels.all():
        channel_data = {
            "channel_number": channel.channel_number,
            "has_transmitter": channel.has_transmitter(),
        }
        if channel.has_transmitter():
            channel_data["transmitter"] = serialize_transmitter(
                channel.transmitter, include_extra=True
            )
        channels.append(channel_data)

    return {
        "api_device_id": receiver.api_device_id,
        "ip": receiver.ip,
        "device_type": receiver.device_type,
        "name": receiver.name,
        "firmware_version": receiver.firmware_version,
        "is_active": receiver.is_active,
        "last_seen": receiver.last_seen.isoformat() if receiver.last_seen else None,
        "health_status": receiver.health_status,
        "is_healthy": receiver.is_healthy,
        "channel_count": receiver.get_channel_count(),
        "channels": channels,
    }
