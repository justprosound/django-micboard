"""Django Channels WebSocket consumers for real-time micboard updates.

This module provides WebSocket consumers for broadcasting device updates to connected clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db.models import F, Q

from micboard.services.notification.realtime_routing_service import (
    GLOBAL_UPDATES_GROUP,
    RealtimeRoutingService,
    campus_updates_group,
    organization_updates_group,
    site_updates_group,
)
from micboard.utils.dependencies import HAS_CHANNELS

if HAS_CHANNELS:
    from channels.generic.websocket import AsyncWebsocketConsumer
else:
    # Channels not installed, provide a stub
    class AsyncWebsocketConsumer:  # type: ignore[no-redef]
        pass


logger = logging.getLogger(__name__)

UNAUTHENTICATED_CLOSE_CODE = 4401
UNAUTHORIZED_CLOSE_CODE = 4403
MESSAGE_TOO_LARGE_CLOSE_CODE = 1009
MAX_WEBSOCKET_COMMAND_BYTES = 4096


class MicboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time device updates."""

    room_group_names: tuple[str, ...]

    @staticmethod
    def _membership_group_names(user_id: int) -> tuple[str, ...]:
        """Resolve active, internally consistent tenant memberships to groups."""
        from micboard.multitenancy.models import OrganizationMembership

        memberships = (
            OrganizationMembership._default_manager.filter(
                user_id=user_id,
                user__is_active=True,
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
        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            memberships = memberships.filter(organization__site_id=settings.SITE_ID)

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

    @staticmethod
    async def _can_receive_global_updates(user: Any) -> bool:
        """Check explicit global-stream permission without blocking the event loop."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(RealtimeRoutingService.can_receive_global_updates)(user)

    @classmethod
    def _current_group_names(cls, user_id: int) -> tuple[str, ...]:
        """Re-resolve an active user's authorized routes from persisted state."""
        from django.contrib.auth import get_user_model

        user = get_user_model()._default_manager.filter(pk=user_id, is_active=True).first()
        if user is None or not user.is_authenticated:
            return ()
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return cls._membership_group_names(user_id)
        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            site_id = RealtimeRoutingService.normalize_identifier(
                getattr(settings, "SITE_ID", None)
            )
            return (site_updates_group(site_id),) if site_id is not None else ()
        if not RealtimeRoutingService.can_receive_global_updates(user):
            return ()
        return (GLOBAL_UPDATES_GROUP,)

    async def _current_groups_for_user(self, user_id: int) -> tuple[str, ...]:
        """Load current outbound authorization without blocking the event loop."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(self._current_group_names)(user_id)

    async def _close_revoked_connection(self, *, code: int, user_id: int | None) -> None:
        """Remove stale group memberships before closing a revoked connection."""
        group_names = getattr(self, "room_group_names", ())
        self.room_group_names = ()
        for group_name in group_names:
            await self.channel_layer.group_discard(group_name, self.channel_name)
        logger.warning(
            "Closed WebSocket after authorization revocation: user_id=%s group_count=%d",
            user_id,
            len(group_names),
        )
        await self.close(code=code)

    async def _can_forward_event(self) -> bool:
        """Fail closed when authentication or any joined route was revoked."""
        user = self.scope.get("user")
        user_id = getattr(user, "pk", None)
        if user is None or not user.is_authenticated or user_id is None:
            await self._close_revoked_connection(
                code=UNAUTHENTICATED_CLOSE_CODE,
                user_id=user_id,
            )
            return False

        joined_groups = getattr(self, "room_group_names", ())
        current_groups = await self._current_groups_for_user(user_id)
        if not joined_groups or not set(joined_groups).issubset(current_groups):
            await self._close_revoked_connection(
                code=UNAUTHORIZED_CLOSE_CODE,
                user_id=user_id,
            )
            return False
        return True

    async def _send_authorized(self, payload: dict[str, Any]) -> None:
        """Revalidate access immediately before forwarding one event."""
        if await self._can_forward_event():
            await self.send(text_data=json.dumps(payload))

    async def connect(self) -> None:
        """Handle WebSocket connection."""
        self.room_group_names = ()
        user = self.scope.get("user")

        if user is None or not user.is_authenticated:
            logger.warning("Rejected unauthenticated WebSocket connection")
            await self.close(code=UNAUTHENTICATED_CLOSE_CODE)
            return
        if not getattr(user, "is_active", False):
            logger.warning("Rejected inactive WebSocket connection: user_id=%s", user.pk)
            await self.close(code=UNAUTHORIZED_CLOSE_CODE)
            return

        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
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
        elif getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            self.room_group_names = (site_updates_group(settings.SITE_ID),)
        else:
            if not await self._can_receive_global_updates(user):
                logger.warning(
                    "Rejected single-site WebSocket connection without global view permission: "
                    "user_id=%s",
                    user.pk,
                )
                await self.close(code=UNAUTHORIZED_CLOSE_CODE)
                return
            self.room_group_names = (GLOBAL_UPDATES_GROUP,)

        for group_name in self.room_group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()
        logger.info(
            "WebSocket connected: user_id=%s group_count=%d",
            user.pk,
            len(self.room_group_names),
        )

    async def disconnect(self, code: int) -> None:
        """Handle WebSocket disconnection."""
        for group_name in getattr(self, "room_group_names", ()):
            await self.channel_layer.group_discard(group_name, self.channel_name)
        user_id = getattr(self.scope.get("user"), "pk", None)
        logger.info("WebSocket disconnected: user_id=%s code=%s", user_id, code)

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        """Handle incoming messages from client."""
        if bytes_data is not None:
            if len(bytes_data) > MAX_WEBSOCKET_COMMAND_BYTES:
                logger.warning(
                    "Rejected oversized binary WebSocket frame: channel=%s bytes=%d",
                    self.channel_name,
                    len(bytes_data),
                )
                await self.close(code=MESSAGE_TOO_LARGE_CLOSE_CODE)
            return

        if text_data is None:
            return

        command_size = len(text_data.encode("utf-8"))
        if command_size > MAX_WEBSOCKET_COMMAND_BYTES:
            logger.warning(
                "Rejected oversized WebSocket command: channel=%s bytes=%d",
                self.channel_name,
                command_size,
            )
            await self.close(code=MESSAGE_TOO_LARGE_CLOSE_CODE)
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning(
                "Rejected malformed WebSocket JSON: channel=%s bytes=%d",
                self.channel_name,
                command_size,
            )
            return

        if not isinstance(data, dict):
            logger.warning(
                "Rejected non-object WebSocket command: channel=%s bytes=%d",
                self.channel_name,
                command_size,
            )
            return

        if data.get("command") == "ping":
            await self._send_authorized({"type": "pong"})

    async def device_update(self, event: dict[str, Any]) -> None:
        """Send device update to WebSocket client."""
        await self._send_authorized({"type": "device_update", "data": event["data"]})

    async def status_update(self, event: dict[str, Any]) -> None:
        """Send status update to WebSocket client."""
        await self._send_authorized({"type": "status", "message": event["message"]})

    async def progress_update(self, event: dict[str, Any]) -> None:
        """Send progress update to WebSocket client."""
        await self._send_authorized({"type": "progress", "status": event.get("status")})

    async def _forward_event(self, event: dict[str, Any]) -> None:
        """Forward a typed Channels event without its internal dispatch key."""
        payload = {key: value for key, value in event.items() if key != "type"}
        await self._send_authorized({"type": event["type"], **payload})

    async def api_health_update(self, event: dict[str, Any]) -> None:
        """Forward a manufacturer API health update."""
        await self._forward_event(event)

    async def device_status_update(self, event: dict[str, Any]) -> None:
        """Forward a persisted hardware status update."""
        await self._forward_event(event)
