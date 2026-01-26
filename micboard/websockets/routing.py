"""Django Channels routing configuration for WebSocket connections.

This module defines the WebSocket URL routing for real-time micboard updates.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws", consumers.MicboardConsumer.as_asgi()),  # type: ignore[arg-type]
]
