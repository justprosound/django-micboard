"""RFChannel model for directional RF communication channels on a wireless chassis.

Each RF channel represents an RF communication path with direction awareness:
  - receive: Field devices send to chassis (traditional wireless mics)
  - send: Chassis sends to field devices (IEM systems)
  - bidirectional: Both directions (hybrid systems like Sennheiser Spectera)
"""

from .compliance import (
    ExclusionZone,
    FrequencyBand,
    RegulatoryDomain,
)
from .rf_channel import RFChannel, RFChannelManager, RFChannelQuerySet

__all__ = [
    "RFChannel",
    "RFChannelManager",
    "RFChannelQuerySet",
    "RegulatoryDomain",
    "FrequencyBand",
    "ExclusionZone",
]
