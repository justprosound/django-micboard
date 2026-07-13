"""Django Channels WebSocket consumers for real-time micboard updates.

This module provides WebSocket consumers for broadcasting device updates to connected clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db.models import F, Q

from micboard.utils.dependencies import HAS_CHANNELS

if HAS_CHANNELS:
    from channels.generic.websocket import AsyncWebsocketConsumer
else:
    # Channels not installed, provide a stub
    class AsyncWebsocketConsumer:  # type: ignore[no-redef]
        pass


logger = logging.getLogger(__name__)

GLOBAL_UPDATES_GROUP = "micboard_updates"
UNAUTHENTICATED_CLOSE_CODE = 4401
UNAUTHORIZED_CLOSE_CODE = 4403


def organization_updates_group(organization_id: int) -> str:
    """Return the realtime group for organization-wide updates."""
    return f"{GLOBAL_UPDATES_GROUP}.organization.{organization_id}"


def campus_updates_group(organization_id: int, campus_id: int) -> str:
    """Return the realtime group for updates restricted to one campus."""
    return f"{organization_updates_group(organization_id)}.campus.{campus_id}"


class MicboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time device updates."""

    @staticmethod
    def _membership_group_names(user_id: int) -> tuple[str, ...]:
        """Resolve active, internally consistent tenant memberships to groups."""
        from micboard.multitenancy.models import OrganizationMembership

        memberships = (
            OrganizationMembership._default_manager.filter(
                user_id=user_id,
                is_active=True,
                organization__is_active=True,
            )
            .filter(
                Q(campus__isnull=True)
                | Q(
                    campus__is_active=True,
                    campus__organization_id=F("organization_id"),
                )
            )
            .values_list("organization_id", "campus_id")
            .order_by("organization_id", "campus_id")
        )

        return tuple(
            campus_updates_group(organization_id, campus_id)
            if campus_id is not None
            else organization_updates_group(organization_id)
            for organization_id, campus_id in memberships
        )

    async def _active_groups_for_user(self, user_id: int) -> tuple[str, ...]:
        """Load active tenant groups without blocking the event loop."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(self._membership_group_names)(user_id)

    async def connect(self) -> None:
        """Handle WebSocket connection."""
        self.room_group_names: tuple[str, ...] = ()
        user = self.scope.get("user")

        if user is None or not user.is_authenticated:
            logger.warning("Rejected unauthenticated WebSocket connection")
            await self.close(code=UNAUTHENTICATED_CLOSE_CODE)
            return

        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            self.room_group_names = (GLOBAL_UPDATES_GROUP,)
        else:
            # Superusers intentionally follow the same membership rules. A global
            # MSP bypass would expose every tenant over a single connection.
            if user.pk is not None:
                self.room_group_names = await self._active_groups_for_user(user.pk)

            if not self.room_group_names:
                logger.warning(
                    "Rejected MSP WebSocket connection without active membership: user_id=%s",
                    user.pk,
                )
                await self.close(code=UNAUTHORIZED_CLOSE_CODE)
                return

        for group_name in self.room_group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()
        logger.info(
            "WebSocket connected: channel=%s groups=%s",
            self.channel_name,
            self.room_group_names,
        )

    async def disconnect(self, code: int) -> None:
        """Handle WebSocket disconnection."""
        for group_name in getattr(self, "room_group_names", ()):
            await self.channel_layer.group_discard(group_name, self.channel_name)
        logger.info("WebSocket disconnected: %s", self.channel_name)

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        """Handle incoming messages from client."""
        if text_data:
            try:
                data = json.loads(text_data)
                # Handle client commands if needed
                command = data.get("command")
                if command == "ping":
                    await self.send(text_data=json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                logger.exception("Invalid JSON received: %s", text_data)

    async def device_update(self, event: dict[str, Any]) -> None:
        """Send device update to WebSocket client."""
        await self.send(text_data=json.dumps({"type": "device_update", "data": event["data"]}))

    async def status_update(self, event: dict[str, Any]) -> None:
        """Send status update to WebSocket client."""
        await self.send(text_data=json.dumps({"type": "status", "message": event["message"]}))

    async def progress_update(self, event: dict[str, Any]) -> None:
        """Send progress update to WebSocket client."""
        await self.send(text_data=json.dumps({"type": "progress", "status": event.get("status")}))
