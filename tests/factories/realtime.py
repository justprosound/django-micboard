"""Factories for real-time connection state."""

from __future__ import annotations

import factory

from micboard.models.realtime.connection import RealTimeConnection

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.RealTimeConnection")
class RealTimeConnectionFactory(ProjectModelFactory):
    """Create a disconnected WebSocket connection for one chassis."""

    class Meta:
        model = RealTimeConnection

    chassis = factory.SubFactory("tests.factories.hardware.WirelessChassisFactory")
    connection_type = "websocket"
