"""Tenant-safe broadcasting for real-time UI updates."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from asgiref.sync import async_to_sync

from micboard.services.notification.realtime_routing_service import (
    RealtimeRoutingService,
    TenantScope,
)
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.utils.exception_logging import sanitized_exception_info

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
                except Exception as exc:
                    logger.exception(
                        "Failed to broadcast realtime event to %s",
                        group_name,
                        exc_info=sanitized_exception_info(exc),
                    )
        except Exception as exc:
            logger.exception(
                "Failed to initialize realtime broadcast",
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    def _send_for_scope(
        cls,
        event: dict[str, Any],
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
        site_id: int | None = None,
    ) -> None:
        """Route one event for a single tenant scope."""
        cls._send_to_groups(
            event,
            RealtimeRoutingService.groups_for_scope(
                organization_id=organization_id,
                campus_id=campus_id,
                site_id=site_id,
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
    def _send_for_sites(cls, event: dict[str, Any], site_ids: Iterable[int]) -> None:
        """Route one event to each explicitly resolved Django Site."""
        groups: list[str] = []
        for site_id in site_ids:
            groups.extend(RealtimeRoutingService.groups_for_scope(site_id=site_id))
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
    def _broadcast_partitioned_site_data(
        cls,
        *,
        manufacturer: Any,
        data: Mapping[str, Any],
    ) -> None:
        """Partition serialized chassis data before routing it by Django Site."""
        receivers = data.get("receivers")
        if not isinstance(receivers, list):
            logger.warning("Skipped multi-site device update without scoped receiver data")
            return

        receiver_ids = {
            identifier
            for receiver in receivers
            if isinstance(receiver, Mapping)
            and (identifier := RealtimeRoutingService.normalize_identifier(receiver.get("id")))
            is not None
        }
        resolved_sites = RealtimeRoutingService.chassis_site_ids(receiver_ids)
        partitions: dict[int, list[Any]] = defaultdict(list)
        for receiver in receivers:
            if not isinstance(receiver, Mapping):
                continue
            site_id = RealtimeRoutingService.normalize_identifier(receiver.get("site_id"))
            if site_id is None:
                receiver_id = RealtimeRoutingService.normalize_identifier(receiver.get("id"))
                site_id = resolved_sites.get(receiver_id) if receiver_id is not None else None
            if site_id is not None:
                partitions[site_id].append(receiver)

        for site_id, scoped_receivers in partitions.items():
            scoped_data = dict(data)
            scoped_data["receivers"] = scoped_receivers
            cls._send_for_scope(
                {"type": "device_update", "data": scoped_data},
                site_id=site_id,
            )

        if not partitions:
            logger.warning(
                "Skipped multi-site device update without a resolvable site: manufacturer=%s",
                getattr(manufacturer, "code", manufacturer),
            )

    @classmethod
    def _broadcast_multisite_device_update(
        cls,
        *,
        manufacturer: Any,
        data: Any,
        chassis_id: int | None,
        site_id: int | None,
    ) -> None:
        """Route one non-MSP device payload within Django Site boundaries."""
        resolved_site_id = site_id
        if resolved_site_id is None and chassis_id is not None:
            resolved_site_id = RealtimeRoutingService.chassis_site_ids((chassis_id,)).get(
                chassis_id
            )
        if resolved_site_id is None and isinstance(data, Mapping):
            resolved_site_id = RealtimeRoutingService.normalize_identifier(data.get("site_id"))
        if resolved_site_id is not None:
            cls._send_for_scope(
                {"type": "device_update", "data": data},
                site_id=resolved_site_id,
            )
        elif isinstance(data, Mapping):
            cls._broadcast_partitioned_site_data(manufacturer=manufacturer, data=data)
        else:
            logger.warning("Skipped multi-site device update without site context")

    @classmethod
    def broadcast_device_update(
        cls,
        *,
        manufacturer: Any,
        data: Any,
        organization_id: int | None = None,
        campus_id: int | None = None,
        chassis_id: int | None = None,
        site_id: int | None = None,
    ) -> None:
        """Broadcast polled device data to authorized WebSocket clients."""
        msp_enabled = micboard_settings.msp_enabled
        multi_site_enabled = micboard_settings.multi_site_mode
        if not (msp_enabled or multi_site_enabled):
            cls._send_for_scope({"type": "device_update", "data": data})
            return

        if not msp_enabled:
            cls._broadcast_multisite_device_update(
                manufacturer=manufacturer,
                data=data,
                chassis_id=chassis_id,
                site_id=site_id,
            )
            return

        scope: TenantScope | None = None
        if organization_id is not None:
            scope = (organization_id, campus_id)
        elif chassis_id is not None:
            scope = RealtimeRoutingService.chassis_tenant_scopes((chassis_id,)).get(chassis_id)
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
        if not micboard_settings.msp_enabled:
            if micboard_settings.multi_site_mode:
                cls._send_for_sites(
                    event,
                    RealtimeRoutingService.manufacturer_site_ids(manufacturer),
                )
            else:
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
        site_id: int | None = None,
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
        msp_enabled = micboard_settings.msp_enabled
        multi_site_enabled = micboard_settings.multi_site_mode
        if msp_enabled:
            scope = (
                (organization_id, campus_id)
                if organization_id is not None
                else RealtimeRoutingService.hardware_tenant_scope(
                    device_type=device_type,
                    device_id=device_id,
                )
            )
        elif multi_site_enabled:
            site_id = site_id or RealtimeRoutingService.hardware_site_id(
                device_type=device_type,
                device_id=device_id,
            )
            if site_id is None:
                logger.warning("Skipped multi-site device status without a resolvable site")
                return
        cls._send_for_scope(
            event,
            organization_id=scope[0] if scope else None,
            campus_id=scope[1] if scope else None,
            site_id=site_id,
        )
