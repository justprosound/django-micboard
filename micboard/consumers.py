import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

logger = logging.getLogger(__name__)


class MicboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time device updates"""
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.room_group_name = 'micboard_updates'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected: {self.channel_name}")
    
    async def disconnect(self, code):
        """Handle WebSocket disconnection"""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected: {self.channel_name}")
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages from client"""
        if text_data:
            try:
                data = json.loads(text_data)
                # Handle client commands if needed
                command = data.get('command')
                if command == 'ping':
                    await self.send(text_data=json.dumps({'type': 'pong'}))
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {text_data}")
    
    async def device_update(self, event):
        """Send device update to WebSocket client"""
        await self.send(text_data=json.dumps({
            'type': 'device_update',
            'data': event['data']
        }))
    
    async def status_update(self, event):
        """Send status update to WebSocket client"""
        await self.send(text_data=json.dumps({
            'type': 'status',
            'message': event['message']
        }))