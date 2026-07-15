"""Persist normalized polling and realtime device updates."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from typing import Any, Protocol

from django.utils import timezone

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.monitoring.alerts import alert_manager
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class DeviceUpdatePlugin(Protocol):
    """Manufacturer transformation operations required by device persistence."""

    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize one raw device payload."""
        raise NotImplementedError

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Return raw channel payloads for one device."""
        raise NotImplementedError

    def transform_transmitter_data(
        self,
        api_data: dict[str, Any],
        channel_number: int,
    ) -> dict[str, Any] | None:
        """Normalize one raw wireless-unit payload."""
        raise NotImplementedError


class DeviceUpdateService:
    """Persist device snapshots without coupling entry points to task modules."""

    @classmethod
    def update_models_from_api_data(
        cls,
        *,
        api_data: Iterable[dict[str, Any]],
        manufacturer: Manufacturer,
        plugin: DeviceUpdatePlugin,
        authoritative_snapshot: bool = False,
    ) -> int:
        """Persist raw API data and return the number of updated chassis.

        Realtime events are partial by default and therefore never mark devices
        absent from one event offline. Full polling snapshots opt into that
        reconciliation with ``authoritative_snapshot=True``.
        """
        updated_count = 0
        active_chassis_ids: list[int] = []
        snapshot_failed = False

        for device_index, device_data in enumerate(api_data, start=1):
            try:
                transformed_data = plugin.transform_device_data(device_data)
                if not transformed_data:
                    snapshot_failed = True
                    continue

                raw_device_id = transformed_data.get("api_device_id") or transformed_data.get("id")
                api_device_id = str(raw_device_id).strip() if raw_device_id is not None else ""
                if not api_device_id:
                    raise ValueError("Transformed device data is missing its identifier")
                defaults = WirelessChassisWrite(
                    ip=transformed_data.get("ip", ""),
                    model=transformed_data.get("type", "unknown"),
                    name=transformed_data.get("name", ""),
                    firmware_version=transformed_data.get("firmware", ""),
                    last_seen=timezone.now(),
                )
                chassis, created = WirelessChassisPersistenceService.upsert(
                    manufacturer=manufacturer,
                    api_device_id=api_device_id,
                    defaults=defaults,
                    create_defaults=defaults.model_copy(update={"status": "online"}),
                )
                cls._reconcile_chassis_lifecycle(
                    chassis=chassis,
                    created=created,
                    manufacturer=manufacturer,
                )
                if chassis.pk is None:  # pragma: no cover - persistence contract guard
                    raise ValueError("Persisted wireless chassis is missing its primary key")
                active_chassis_ids.append(chassis.pk)

                embedded_channels = transformed_data.get("channels")
                if isinstance(embedded_channels, list) and embedded_channels:
                    channel_data_items = embedded_channels
                    transmitter_is_normalized = True
                else:
                    channel_data_items = plugin.get_device_channels(api_device_id)
                    transmitter_is_normalized = False

                for channel_data in channel_data_items:
                    cls._update_channel_and_unit(
                        chassis=chassis,
                        channel_data=channel_data,
                        plugin=plugin,
                        api_device_id=api_device_id,
                        transmitter_is_normalized=transmitter_is_normalized,
                    )
                updated_count += 1
            except Exception as exc:
                snapshot_failed = True
                logger.exception(
                    "Error updating vendor device at snapshot position %s",
                    device_index,
                    exc_info=sanitized_exception_info(exc),
                )

        if authoritative_snapshot and not snapshot_failed:
            cls.mark_offline_receivers(
                manufacturer=manufacturer,
                active_chassis_ids=active_chassis_ids,
            )
        elif authoritative_snapshot:
            logger.warning(
                "Skipped offline reconciliation for %s because the snapshot was incomplete",
                manufacturer.code,
            )
        return updated_count

    @staticmethod
    def _reconcile_chassis_lifecycle(
        *,
        chassis: WirelessChassis,
        created: bool,
        manufacturer: Manufacturer,
    ) -> None:
        """Log one upsert and restore the expected operational lifecycle state."""
        from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager

        lifecycle = HardwareLifecycleManager()
        if created:
            logger.info(
                "Created wireless chassis %s for manufacturer %s",
                chassis.pk,
                manufacturer.pk,
            )
        else:
            logger.debug(
                "Updated wireless chassis %s for manufacturer %s",
                chassis.pk,
                manufacturer.pk,
            )
            if chassis.status not in {"online", "degraded", "maintenance"}:
                if chassis.status == "discovered" and not lifecycle.transition_device(
                    chassis,
                    "provisioning",
                    reason="Device responding to polls",
                ):
                    raise RuntimeError(f"Could not provision wireless chassis {chassis.pk}")
                if not lifecycle.mark_online(chassis):
                    raise RuntimeError(f"Could not mark wireless chassis {chassis.pk} online")
                chassis.refresh_from_db(
                    fields=["status", "is_online", "last_online_at", "last_seen"]
                )

    @classmethod
    def _update_channel_and_unit(
        cls,
        *,
        chassis: WirelessChassis,
        channel_data: dict[str, Any],
        plugin: DeviceUpdatePlugin,
        api_device_id: str,
        transmitter_is_normalized: bool = False,
    ) -> None:
        """Update one RF channel and its attached wireless unit."""
        channel_number = int(channel_data.get("channel", 0))
        raw_unit = channel_data.get("tx")
        if not isinstance(raw_unit, dict):
            return

        transformed_unit = (
            raw_unit
            if transmitter_is_normalized
            else plugin.transform_transmitter_data(raw_unit, channel_number)
        )
        if not transformed_unit:
            return

        channel, created = RFChannel.objects.update_or_create(
            chassis=chassis,
            channel_number=channel_number,
        )
        if created:
            logger.info(
                "Created RF channel %s for wireless chassis %s",
                channel.pk,
                chassis.pk,
            )

        slot = cls._assign_unit_slot(
            channel=channel,
            transformed_unit=transformed_unit,
            api_device_id=api_device_id,
            channel_number=channel_number,
        )
        unit, _ = WirelessUnit.objects.update_or_create(
            assigned_resource=channel,
            defaults={
                "slot": slot,
                "manufacturer": chassis.manufacturer,
                "base_chassis": chassis,
                "battery": (
                    transformed_unit["battery"]
                    if transformed_unit.get("battery") is not None
                    else 255
                ),
                "battery_charge": transformed_unit.get("battery_charge"),
                "battery_type": transformed_unit.get("battery_type") or "",
                "battery_runtime": transformed_unit.get("runtime") or "",
                "battery_health": transformed_unit.get("battery_health") or "",
                "battery_cycles": transformed_unit.get("battery_cycles"),
                "battery_temperature_c": transformed_unit.get("battery_temperature_c"),
                "audio_level": transformed_unit.get("audio_level") or 0,
                "rf_level": transformed_unit.get("rf_level") or 0,
                "frequency": transformed_unit.get("frequency") or "",
                "antenna": transformed_unit.get("antenna") or "",
                "tx_offset": (
                    transformed_unit["tx_offset"]
                    if transformed_unit.get("tx_offset") is not None
                    else 255
                ),
                "quality": (
                    transformed_unit["quality"]
                    if transformed_unit.get("quality") is not None
                    else 255
                ),
                "status": transformed_unit.get("status") or "",
                "name": transformed_unit.get("name") or "",
            },
        )
        alert_manager.check_wireless_unit_alerts(unit)

    @staticmethod
    def _assign_unit_slot(
        *,
        channel: RFChannel,
        transformed_unit: dict[str, Any],
        api_device_id: str,
        channel_number: int,
    ) -> int:
        """Reuse an assigned slot or derive a stable collision-free slot."""
        existing = WirelessUnit.objects.filter(assigned_resource=channel).only("slot").first()
        if existing is not None:
            logger.debug(
                "Reusing slot %d for RF channel %s",
                existing.slot,
                channel.pk,
            )
            return existing.slot

        api_slot = transformed_unit.get("slot")
        if api_slot is not None:
            return int(api_slot)

        digest = hashlib.sha256(f"{api_device_id}:{channel_number}".encode()).digest()
        slot = int.from_bytes(digest[:4], byteorder="big") % 10000
        while WirelessUnit.objects.filter(slot=slot).exists():
            slot = (slot + 1) % 10000
        logger.info("Assigned slot %d for RF channel %s", slot, channel.pk)
        return slot

    @staticmethod
    def mark_offline_receivers(
        *,
        manufacturer: Manufacturer,
        active_chassis_ids: Iterable[int],
    ) -> None:
        """Mark chassis missing from an authoritative snapshot offline."""
        from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager

        offline_chassis = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status__in={"online", "degraded", "provisioning"},
        ).exclude(id__in=active_chassis_ids)
        if not offline_chassis.exists():
            return

        lifecycle = HardwareLifecycleManager()
        offline_count = 0
        for chassis in offline_chassis:
            try:
                lifecycle.mark_offline(chassis, reason="Device not found in API poll")
                offline_count += 1
            except Exception as exc:
                logger.exception(
                    "Error marking wireless chassis %s offline",
                    chassis.pk,
                    exc_info=sanitized_exception_info(exc),
                )

        if not offline_count:
            return
        logger.warning(
            "Marked %d chassis offline for manufacturer %s",
            offline_count,
            manufacturer.pk,
        )
        refreshed_chassis = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status="offline",
        ).prefetch_related("field_units")
        for chassis in refreshed_chassis:
            for unit in chassis.field_units.all():
                alert_manager.check_hardware_offline_alerts(unit)
