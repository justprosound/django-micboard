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
from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis, NormalizedUnit
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.monitoring.alerts import alert_manager
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class DeviceUpdatePlugin(Protocol):
    """Manufacturer operations required by device persistence."""

    def normalize_device(self, api_data: dict[str, Any]) -> NormalizedChassis | None:
        """Normalize one raw device payload."""
        raise NotImplementedError

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Return raw channel payloads for one device."""
        raise NotImplementedError

    def normalize_channels(self, api_channels: list[dict[str, Any]]) -> list[NormalizedChannel]:
        """Normalize a raw channel list."""
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
                device = plugin.normalize_device(device_data)
                if device is None:
                    snapshot_failed = True
                    continue

                api_device_id = device.api_device_id
                write_values: dict[str, Any] = {
                    "ip": device.ip,
                    "name": device.name,
                    "firmware_version": device.firmware_version,
                    "last_seen": timezone.now(),
                }
                # Realtime events often omit the model; an empty one must not erase a known model.
                if device.model:
                    write_values["model"] = device.model
                defaults = WirelessChassisWrite(**write_values)
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

                channels = device.channels or plugin.normalize_channels(
                    plugin.get_device_channels(api_device_id)
                )
                for channel in channels:
                    if channel.unit is not None:
                        cls._update_channel_and_unit(
                            chassis=chassis,
                            channel_number=channel.number,
                            unit_data=channel.unit,
                            api_device_id=api_device_id,
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
        channel_number: int,
        unit_data: NormalizedUnit,
        api_device_id: str,
    ) -> None:
        """Update one RF channel and its attached wireless unit."""
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
            api_slot=unit_data.slot,
            api_device_id=api_device_id,
            channel_number=channel_number,
        )
        unit, _ = WirelessUnit.objects.update_or_create(
            assigned_resource=channel,
            defaults={
                "slot": slot,
                "manufacturer": chassis.manufacturer,
                "base_chassis": chassis,
                "battery": unit_data.battery,
                "battery_charge": unit_data.battery_charge,
                "battery_type": unit_data.battery_type,
                "battery_runtime": unit_data.runtime,
                "battery_health": unit_data.battery_health,
                "battery_cycles": unit_data.battery_cycles,
                "battery_temperature_c": unit_data.battery_temperature_c,
                "audio_level": unit_data.audio_level,
                "rf_level": unit_data.rf_level,
                "frequency": unit_data.frequency,
                "antenna": unit_data.antenna,
                "tx_offset": unit_data.tx_offset,
                "quality": unit_data.quality,
                "status": unit_data.status,
                "name": unit_data.name,
            },
        )
        alert_manager.check_wireless_unit_alerts(unit)

    @staticmethod
    def _assign_unit_slot(
        *,
        channel: RFChannel,
        api_slot: int | None,
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
