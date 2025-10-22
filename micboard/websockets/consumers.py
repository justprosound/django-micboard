"""
Django Channels WebSocket consumers for real-time micboard updates.

This module provides WebSocket consumers for broadcasting device updates to connected clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class MicboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time device updates"""

    async def connect(self):
        """Handle WebSocket connection"""
        self.room_group_name = "micboard_updates"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        logger.info(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, code: int):
        """Handle WebSocket disconnection"""
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        logger.info(f"WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None):
        """Handle incoming messages from client"""
        if text_data:
            try:
                data = json.loads(text_data)
                # Handle client commands if needed
                command = data.get("command")
                if command == "ping":
                    await self.send(text_data=json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                logger.exception("Invalid JSON received: %s", text_data)

    async def device_update(self, event: dict[str, Any]):
        """Send device update to WebSocket client"""
        await self.send(text_data=json.dumps({"type": "device_update", "data": event["data"]}))

    async def status_update(self, event: dict[str, Any]):
        """Send status update to WebSocket client"""
        await self.send(text_data=json.dumps({"type": "status", "message": event["message"]}))

    async def progress_update(self, event: dict[str, Any]):
        """Send progress update to WebSocket client"""
        await self.send(text_data=json.dumps({"type": "progress", "status": event.get("status")}))
