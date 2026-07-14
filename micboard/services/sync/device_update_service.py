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
from micboard.services.monitoring.alerts import (
    check_hardware_offline_alerts,
    check_transmitter_alerts,
)

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

        for device_data in api_data:
            device_identifier = str(
                device_data.get("api_device_id") or device_data.get("id") or "unknown"
            )
            try:
                transformed_data = plugin.transform_device_data(device_data)
                if not transformed_data:
                    snapshot_failed = True
                    continue

                raw_device_id = transformed_data.get("api_device_id") or transformed_data.get("id")
                api_device_id = str(raw_device_id).strip() if raw_device_id is not None else ""
                if not api_device_id:
                    raise ValueError("Transformed device data is missing its identifier")
                chassis = cls._update_chassis(
                    transformed_data=transformed_data,
                    manufacturer=manufacturer,
                    api_device_id=api_device_id,
                )
                if chassis.pk is None:  # pragma: no cover - persistence contract guard
                    raise ValueError("Persisted wireless chassis is missing its primary key")
                active_chassis_ids.append(chassis.pk)

                for channel_data in plugin.get_device_channels(api_device_id):
                    cls._update_channel_and_unit(
                        chassis=chassis,
                        channel_data=channel_data,
                        plugin=plugin,
                        api_device_id=api_device_id,
                    )
                updated_count += 1
            except Exception:
                snapshot_failed = True
                logger.exception("Error updating device %s", device_identifier)

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
    def _update_chassis(
        *,
        transformed_data: dict[str, Any],
        manufacturer: Manufacturer,
        api_device_id: str,
    ) -> WirelessChassis:
        """Update or create one wireless chassis from normalized data."""
        from micboard.services.core.hardware_lifecycle import get_lifecycle_manager

        defaults = {
            "ip": transformed_data.get("ip", ""),
            "model": transformed_data.get("type", "unknown"),
            "name": transformed_data.get("name", ""),
            "firmware_version": transformed_data.get("firmware", ""),
            "last_seen": timezone.now(),
        }
        chassis, created = WirelessChassis.objects.update_or_create(
            api_device_id=api_device_id,
            manufacturer=manufacturer,
            defaults=defaults,
            create_defaults={**defaults, "status": "online"},
        )

        lifecycle = get_lifecycle_manager(manufacturer.code)
        if created:
            logger.info("Created new wireless chassis: %s (%s)", chassis.name, api_device_id)
        else:
            logger.debug("Updated wireless chassis: %s", api_device_id)
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
        return chassis

    @classmethod
    def _update_channel_and_unit(
        cls,
        *,
        chassis: WirelessChassis,
        channel_data: dict[str, Any],
        plugin: DeviceUpdatePlugin,
        api_device_id: str,
    ) -> None:
        """Update one RF channel and its attached wireless unit."""
        channel_number = int(channel_data.get("channel", 0))
        raw_unit = channel_data.get("tx")
        if not isinstance(raw_unit, dict):
            return

        transformed_unit = plugin.transform_transmitter_data(raw_unit, channel_number)
        if not transformed_unit:
            return

        channel, created = RFChannel.objects.update_or_create(
            chassis=chassis,
            channel_number=channel_number,
        )
        if created:
            logger.info(
                "Created channel %d for wireless chassis %s",
                channel_number,
                chassis.name,
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
                "battery": transformed_unit.get("battery", 255),
                "battery_charge": transformed_unit.get("battery_charge"),
                "battery_type": transformed_unit.get("battery_type", ""),
                "battery_runtime": transformed_unit.get("runtime", ""),
                "battery_health": transformed_unit.get("battery_health", ""),
                "battery_cycles": transformed_unit.get("battery_cycles"),
                "battery_temperature_c": transformed_unit.get("battery_temperature_c"),
                "audio_level": transformed_unit.get("audio_level", 0),
                "rf_level": transformed_unit.get("rf_level", 0),
                "frequency": transformed_unit.get("frequency", ""),
                "antenna": transformed_unit.get("antenna", ""),
                "tx_offset": transformed_unit.get("tx_offset", 255),
                "quality": transformed_unit.get("quality", 255),
                "status": transformed_unit.get("status", ""),
                "name": transformed_unit.get("name", ""),
            },
        )
        check_transmitter_alerts(unit)

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
                "Reusing slot %d for %s channel %d",
                existing.slot,
                api_device_id,
                channel_number,
            )
            return existing.slot

        api_slot = transformed_unit.get("slot")
        if api_slot is not None:
            return int(api_slot)

        digest = hashlib.sha256(f"{api_device_id}:{channel_number}".encode()).digest()
        slot = int.from_bytes(digest[:4], byteorder="big") % 10000
        while WirelessUnit.objects.filter(slot=slot).exists():
            slot = (slot + 1) % 10000
        logger.info("Assigned slot %d for %s channel %d", slot, api_device_id, channel_number)
        return slot

    @staticmethod
    def mark_offline_receivers(
        *,
        manufacturer: Manufacturer,
        active_chassis_ids: Iterable[int],
    ) -> None:
        """Mark chassis missing from an authoritative snapshot offline."""
        from micboard.services.core.hardware_lifecycle import get_lifecycle_manager

        offline_chassis = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status__in={"online", "degraded", "provisioning"},
        ).exclude(id__in=active_chassis_ids)
        if not offline_chassis.exists():
            return

        lifecycle = get_lifecycle_manager(manufacturer.code)
        offline_count = 0
        for chassis in offline_chassis:
            try:
                lifecycle.mark_offline(chassis, reason="Device not found in API poll")
                offline_count += 1
            except Exception:
                logger.exception("Error marking wireless chassis %s offline", chassis.pk)

        if not offline_count:
            return
        logger.warning("Marked %d chassis offline for %s", offline_count, manufacturer.name)
        refreshed_chassis = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status="offline",
        ).prefetch_related("field_units")
        for chassis in refreshed_chassis:
            for unit in chassis.field_units.all():
                check_hardware_offline_alerts(unit)
