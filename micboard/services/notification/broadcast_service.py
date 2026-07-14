"""Tenant-safe broadcasting for real-time UI updates."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from django.conf import settings

from asgiref.sync import async_to_sync

from micboard.services.notification.realtime_routing_service import (
    RealtimeRoutingService,
    TenantScope,
)

if TYPE_CHECKING:
    from channels.layers import BaseChannelLayer  # pragma: no cover

try:
    from channels.layers import get_channel_layer
except ImportError:

    def get_channel_layer(alias: str = "") -> BaseChannelLayer | None:
        """Return no layer when the optional Channels dependency is absent."""
        return None


logger = logging.getLogger(__name__)


class BroadcastService:
    """Route real-time events without crossing tenant boundaries."""

    @staticmethod
    def _send_to_groups(event: dict[str, Any], groups: Iterable[str]) -> None:
        """Send an event to each unique group when Channels is configured."""
        unique_groups = tuple(dict.fromkeys(groups))
        if not unique_groups:
            logger.warning("Skipped realtime event without an authorized tenant route")
            return

        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.debug("No channel layer configured; skipping realtime broadcast")
                return

            send = async_to_sync(channel_layer.group_send)
            for group_name in unique_groups:
                try:
                    send(group_name, event)
                except Exception:
                    logger.exception("Failed to broadcast realtime event to %s", group_name)
        except Exception:
            logger.exception("Failed to initialize realtime broadcast")

    @classmethod
    def _send_for_scope(
        cls,
        event: dict[str, Any],
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Route one event for a single tenant scope."""
        cls._send_to_groups(
            event,
            RealtimeRoutingService.groups_for_scope(
                organization_id=organization_id,
                campus_id=campus_id,
            ),
        )

    @classmethod
    def _send_for_scopes(
        cls,
        event: dict[str, Any],
        scopes: Iterable[TenantScope],
    ) -> None:
        """Route one event to every group represented by tenant scopes."""
        groups: list[str] = []
        for organization_id, campus_id in scopes:
            groups.extend(
                RealtimeRoutingService.groups_for_scope(
                    organization_id=organization_id,
                    campus_id=campus_id,
                )
            )
        cls._send_to_groups(event, groups)

    @classmethod
    def _broadcast_partitioned_device_data(
        cls,
        *,
        manufacturer: Any,
        data: Mapping[str, Any],
    ) -> None:
        """Partition serialized chassis data before routing it to tenants."""
        receivers = data.get("receivers")
        if not isinstance(receivers, list):
            logger.warning("Skipped MSP device update without scoped receiver data")
            return

        receiver_ids = {
            identifier
            for receiver in receivers
            if isinstance(receiver, Mapping)
            and (identifier := RealtimeRoutingService.normalize_identifier(receiver.get("id")))
            is not None
        }
        resolved_scopes = RealtimeRoutingService.chassis_tenant_scopes(receiver_ids)
        partitions: dict[TenantScope, list[Any]] = defaultdict(list)

        for receiver in receivers:
            if not isinstance(receiver, Mapping):
                continue
            scope = RealtimeRoutingService.scope_from_mapping(receiver)
            if scope is None:
                receiver_id = RealtimeRoutingService.normalize_identifier(receiver.get("id"))
                scope = resolved_scopes.get(receiver_id) if receiver_id is not None else None
            if scope is not None:
                partitions[scope].append(receiver)

        for (organization_id, campus_id), scoped_receivers in partitions.items():
            scoped_data = dict(data)
            scoped_data["receivers"] = scoped_receivers
            cls._send_for_scope(
                {"type": "device_update", "data": scoped_data},
                organization_id=organization_id,
                campus_id=campus_id,
            )

        if not partitions:
            logger.warning(
                "Skipped MSP device update without a resolvable tenant: manufacturer=%s",
                getattr(manufacturer, "code", manufacturer),
            )

    @classmethod
    def broadcast_device_update(
        cls,
        *,
        manufacturer: Any,
        data: Any,
        organization_id: int | None = None,
        campus_id: int | None = None,
        chassis_id: int | None = None,
    ) -> None:
        """Broadcast polled device data to authorized WebSocket clients."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            cls._send_for_scope({"type": "device_update", "data": data})
            return

        scope: TenantScope | None = None
        if organization_id is not None:
            scope = (organization_id, campus_id)
        elif chassis_id is not None:
            scope = RealtimeRoutingService.chassis_tenant_scope(chassis_id)
        elif isinstance(data, Mapping):
            scope = RealtimeRoutingService.scope_from_mapping(data)

        if scope is not None:
            cls._send_for_scope(
                {"type": "device_update", "data": data},
                organization_id=scope[0],
                campus_id=scope[1],
            )
            return

        if isinstance(data, Mapping):
            cls._broadcast_partitioned_device_data(manufacturer=manufacturer, data=data)
            return

        logger.warning("Skipped MSP device update without tenant context")

    @classmethod
    def broadcast_api_health(cls, *, manufacturer: Any, health_data: dict[str, Any]) -> None:
        """Broadcast API health only to tenants using the manufacturer."""
        event = {
            "type": "api_health_update",
            "manufacturer_code": getattr(manufacturer, "code", None),
            "health_data": health_data,
        }
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            cls._send_for_scope(event)
            return
        cls._send_for_scopes(event, RealtimeRoutingService.manufacturer_tenant_scopes(manufacturer))

    @classmethod
    def broadcast_device_status(
        cls,
        *,
        service_code: str,
        device_id: int,
        device_type: str,
        status: str,
        is_active: bool,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast a device status change within its chassis tenant."""
        event = {
            "type": "device_status_update",
            "service_code": service_code,
            "device_id": device_id,
            "device_type": device_type,
            "status": status,
            "is_active": is_active,
        }
        scope = None
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            scope = (
                (organization_id, campus_id)
                if organization_id is not None
                else RealtimeRoutingService.hardware_tenant_scope(
                    device_type=device_type,
                    device_id=device_id,
                )
            )
        cls._send_for_scope(
            event,
            organization_id=scope[0] if scope else None,
            campus_id=scope[1] if scope else None,
        )

    @classmethod
    def broadcast_sync_completion(
        cls,
        *,
        service_code: str,
        sync_result: dict[str, Any],
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast tenant-scoped sync completion."""
        scope = (
            (organization_id, campus_id)
            if organization_id is not None
            else RealtimeRoutingService.scope_from_mapping(sync_result)
        )
        cls._send_for_scope(
            {
                "type": "sync_completed",
                "service_code": service_code,
                "device_count": sync_result.get("device_count", 0),
                "online_count": sync_result.get("online_count", 0),
                "status": sync_result.get("status", "success"),
            },
            organization_id=scope[0] if scope else None,
            campus_id=scope[1] if scope else None,
        )

    @classmethod
    def broadcast_discovery_approved(
        cls,
        *,
        queue_item_id: int,
        manufacturer_code: str,
        device_count: int,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast tenant-scoped discovery approval."""
        cls._send_for_scope(
            {
                "type": "discovery_approved",
                "queue_item_id": queue_item_id,
                "manufacturer_code": manufacturer_code,
                "device_count": device_count,
            },
            organization_id=organization_id,
            campus_id=campus_id,
        )

    @classmethod
    def broadcast_error(
        cls,
        *,
        error_type: str,
        error_message: str,
        manufacturer_code: str | None = None,
        device_id: int | None = None,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast an error notification within its tenant."""
        from django.utils import timezone

        scope = None
        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            if organization_id is not None:
                scope = (organization_id, campus_id)
            elif device_id is not None:
                scope = RealtimeRoutingService.hardware_tenant_scope(
                    device_type="WirelessChassis",
                    device_id=device_id,
                )
        cls._send_for_scope(
            {
                "type": "error_notification",
                "error_type": error_type,
                "message": error_message,
                "manufacturer_code": manufacturer_code,
                "device_id": device_id,
                "timestamp": timezone.now().isoformat(),
            },
            organization_id=scope[0] if scope else None,
            campus_id=scope[1] if scope else None,
        )

    @classmethod
    def broadcast_progress_update(
        cls,
        *,
        status: Any,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Broadcast discovery progress when its tenant is explicit."""
        cls._send_for_scope(
            {"type": "progress_update", "status": status},
            organization_id=organization_id,
            campus_id=campus_id,
        )
