# High-level functional API (backwards-compatible helpers)
from .compat import (
    serialize_channel,
    serialize_discovered_device,
    serialize_group,
    serialize_receiver,
    serialize_receiver_detail,
    serialize_receiver_summary,
    serialize_receivers,
    serialize_transmitter,
)
from .serializers import (
    ChannelSerializer,
    DeviceAssignmentSerializer,
    DiscoveredDeviceSerializer,
    GroupSerializer,
    ReceiverDetailSerializer,
    ReceiverSummarySerializer,
    TransmitterSerializer,
)

__all__ = [
    # DRF serializer classes
    "ChannelSerializer",
    "DeviceAssignmentSerializer",
    "DiscoveredDeviceSerializer",
    "GroupSerializer",
    "ReceiverDetailSerializer",
    "ReceiverSummarySerializer",
    "TransmitterSerializer",
    # Functional helpers
    "serialize_channel",
    "serialize_discovered_device",
    "serialize_group",
    "serialize_receiver",
    "serialize_receiver_detail",
    "serialize_receiver_summary",
    "serialize_receivers",
    "serialize_transmitter",
]
