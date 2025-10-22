"""Compatibility serializer helpers expected by tests and older code.

These functions delegate to the DRF ModelSerializers defined in
`micboard.serializers.serializers` but provide the simple function API used
throughout the test suite.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from micboard.models import Channel, DiscoveredDevice, Group, Receiver, Transmitter
from micboard.serializers.serializers import (
    ChannelSerializer,
    DiscoveredDeviceSerializer,
    GroupSerializer,
    ReceiverDetailSerializer,
    ReceiverSummarySerializer,
    TransmitterSerializer,
)


def _ensure_iterable(obj):
    if obj is None:
        return []
    if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        return obj
    return [obj]


def serialize_transmitter(transmitter: Transmitter, include_extra: bool = False) -> dict[str, Any]:
    data = TransmitterSerializer(transmitter).data
    if not include_extra:
        # remove extra computed fields
        for k in ("battery_health", "signal_quality", "is_active"):
            data.pop(k, None)
    return cast(dict[str, Any], data)


def serialize_channel(channel: Channel, include_extra: bool = False) -> dict[str, Any]:
    data = ChannelSerializer(channel).data
    # If there is a transmitter object but include_extra is False, remove
    # computed extra fields. If transmitter is None and include_extra is False,
    # remove the key entirely to match legacy serializer behaviour expected by tests.
    if "transmitter" in data:
        if data["transmitter"] is None and not include_extra:
            data.pop("transmitter", None)
        elif data["transmitter"] is not None and not include_extra:
            for k in ("battery_health", "signal_quality", "is_active"):
                data["transmitter"].pop(k, None)
    return cast(dict[str, Any], data)


def serialize_receiver(receiver: Receiver, include_extra: bool = False) -> dict[str, Any]:
    # Use detail serializer when include_extra True to include channels
    if include_extra:
        data = ReceiverDetailSerializer(receiver).data
    else:
        data = ReceiverSummarySerializer(receiver).data
    return cast(dict[str, Any], data)


def serialize_receiver_summary(receiver: Receiver) -> dict[str, Any]:
    return cast(dict[str, Any], ReceiverSummarySerializer(receiver).data)


def serialize_receiver_detail(receiver: Receiver) -> dict[str, Any]:
    data = ReceiverDetailSerializer(receiver).data
    # Clean up channels: when a channel has no transmitter, omit the key to match
    # legacy serialized shape expected by tests.
    channels = data.get("channels")
    if isinstance(channels, list):
        for ch in channels:
            if ch.get("transmitter") is None:
                ch.pop("transmitter", None)
    return cast(dict[str, Any], data)


def serialize_receivers(
    receivers: Iterable[Receiver] | None = None,
    *,
    include_extra: bool = False,
    manufacturer_code: str | None = None,
) -> list[dict[str, Any]]:
    if receivers is None:
        # Default behaviour: if a manufacturer_code is provided, return all
        # receivers for that manufacturer (including inactive). Otherwise
        # return only active receivers.
        if manufacturer_code:
            qs = Receiver.objects.filter(manufacturer__code=manufacturer_code)
        else:
            qs = Receiver.objects.filter(is_active=True)
        receivers = qs

    receivers = list(receivers)
    # DEBUG: help diagnose failing test that expects multiple receivers
    # Remove these prints once the issue is fixed.
    try:
        print("serialize_receivers - receivers count:", len(receivers))
        print("serialize_receivers - receivers:", [r.name for r in receivers])
    except Exception:
        pass
    if include_extra:
        out = []
        for r in receivers:
            try:
                d = ReceiverDetailSerializer(r).data
                # Clean channels as above
                channels = d.get("channels")
                if isinstance(channels, list):
                    for ch in channels:
                        if ch.get("transmitter") is None:
                            ch.pop("transmitter", None)
                out.append(d)
            except Exception as exc:
                print(
                    f"serialize_receivers: failed to serialize receiver {getattr(r, 'name', None)}: {exc}"
                )
        print("serialize_receivers: returning", len(out), "items (include_extra)")
        return cast(list[dict[str, Any]], out)
    out = []
    for r in receivers:
        try:
            s = ReceiverSummarySerializer(r).data
            out.append(s)
            print(f"serialize_receivers: serialized {r.name} -> {s.get('api_device_id')}")
        except Exception as exc:
            print(
                f"serialize_receivers: failed to summary-serialize {getattr(r, 'name', None)}: {exc}"
            )
    print("serialize_receivers: returning", len(out), "items (summary)")
    return cast(list[dict[str, Any]], out)


def serialize_discovered_device(device: DiscoveredDevice) -> dict[str, Any]:
    return cast(dict[str, Any], DiscoveredDeviceSerializer(device).data)


def serialize_group(group: Group) -> dict[str, Any]:
    return cast(dict[str, Any], GroupSerializer(group).data)


__all__ = [
    "serialize_channel",
    "serialize_discovered_device",
    "serialize_group",
    "serialize_receiver",
    "serialize_receiver_detail",
    "serialize_receiver_summary",
    "serialize_receivers",
    "serialize_transmitter",
]
