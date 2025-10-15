"""
Django Channels routing configuration for WebSocket connections.

This module defines the WebSocket URL routing for real-time micboard updates.
"""
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws$", consumers.MicboardConsumer.as_asgi()),
]
