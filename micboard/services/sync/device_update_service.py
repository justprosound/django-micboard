"""Persist realtime and API-server device updates with their channels and units."""

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.core.hardware import NormalizedChannel, NormalizedUnit
from micboard.services.monitoring.alerts import alert_manager
from micboard.services.sync.chassis_ingest import ChassisIngestService, IngestedChassis, IngestMode
from micboard.services.sync.chassis_normalization import ChassisNormalizer
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class DeviceUpdatePlugin(ChassisNormalizer, Protocol):
    """Manufacturer operations required by device persistence."""

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Return raw channel payloads for one device."""
        raise NotImplementedError

    def normalize_channels(self, api_channels: list[dict[str, Any]]) -> list[NormalizedChannel]:
        """Normalize a raw channel list."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeviceUpdateResult:
    """What one device update persisted and what it could not."""

    persisted: int = 0
    skipped: int = 0
    rejected: int = 0
    failed: int = 0
    persisted_api_device_ids: tuple[str, ...] = ()

    @property
    def dropped(self) -> int:
        """Number of payloads that were not persisted."""
        return self.skipped + self.rejected + self.failed


class DeviceUpdateService:
    """Persist realtime and API-server device updates, with their channels and units."""

    @classmethod
    def update_models_from_api_data(
        cls,
        *,
        api_data: Iterable[dict[str, Any]],
        manufacturer: Manufacturer,
        plugin: DeviceUpdatePlugin,
        mode: IngestMode = IngestMode.PARTIAL_EVENT,
    ) -> DeviceUpdateResult:
        """Persist raw API data and report what was persisted and what was dropped.

        Realtime events are partial by default and therefore never mark devices absent
        from one event offline. A complete snapshot opts into that reconciliation with
        `IngestMode.AUTHORITATIVE_SNAPSHOT`, unless ingest could not read every device.
        """
        result = ChassisIngestService.ingest(
            api_data,
            plugin=plugin,
            manufacturer=manufacturer,
            mode=mode,
            require_active=False,
        )
        for entry in result.ingested:
            cls._persist_channels(entry, plugin)
        outcome = DeviceUpdateResult(
            persisted=len(result.ingested),
            skipped=result.skipped,
            rejected=result.rejected,
            failed=result.failed + result.unnormalizable,
            persisted_api_device_ids=tuple(
                entry.payload.api_device_id for entry in result.ingested
            ),
        )
        if outcome.dropped:
            logger.warning(
                "Device update for manufacturer ID %s dropped %d payload(s): "
                "%d skipped, %d rejected, %d failed",
                manufacturer.pk,
                outcome.dropped,
                outcome.skipped,
                outcome.rejected,
                outcome.failed,
            )
        return outcome

    @classmethod
    def _persist_channels(cls, entry: IngestedChassis, plugin: DeviceUpdatePlugin) -> None:
        """Persist the channels and units one ingested payload reported."""
        api_device_id = entry.payload.api_device_id
        try:
            channels = entry.payload.channels or plugin.normalize_channels(
                plugin.get_device_channels(api_device_id)
            )
            for channel in channels:
                if channel.unit is not None:
                    cls._update_channel_and_unit(
                        chassis=entry.chassis,
                        channel_number=channel.number,
                        unit_data=channel.unit,
                        api_device_id=api_device_id,
                    )
        except Exception as exc:
            logger.exception(
                "Error updating channels for wireless chassis %s",
                entry.chassis.pk,
                exc_info=sanitized_exception_info(exc),
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
