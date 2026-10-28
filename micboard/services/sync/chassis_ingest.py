"""Identity-safe ingest of normalized chassis from every source.

The poll, realtime and API-server paths all persist what a manufacturer reported through
`ChassisIngestService.ingest`, so a chassis already known under another identity (serial,
MAC, address or API id) is matched, moved or rejected the same way whichever path saw it.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from django.db import transaction

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager, HardwareStatus
from micboard.services.deduplication.check import check_device
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
)
from micboard.services.deduplication.tracking import log_device_movement
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.monitoring.alerts import alert_manager
from micboard.services.sync.discovery_trigger_service import coalesce_discovery_scheduling
from micboard.utils.exception_logging import sanitized_exception_info
from micboard.utils.mac_address import canonicalize_mac_address

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.services.core.hardware import NormalizedChassis

logger = logging.getLogger(__name__)

IngestOutcome = Literal["created", "updated"]


class IngestMode(StrEnum):
    """What the payloads say about chassis they do not mention."""

    PARTIAL_EVENT = "partial_event"
    """Payloads are part of the inventory; absent chassis keep their state."""

    AUTHORITATIVE_SNAPSHOT = "authoritative_snapshot"
    """Payloads are the manufacturer's complete inventory; absent chassis go offline."""


@dataclass(frozen=True, slots=True)
class IngestedChassis:
    """One payload and the chassis it was persisted as."""

    payload: NormalizedChassis
    chassis: WirelessChassis
    outcome: IngestOutcome


@dataclass(slots=True)
class ChassisIngestResult:
    """What one ingest persisted, skipped and failed."""

    ingested: list[IngestedChassis] = field(default_factory=list)
    failed: int = 0
    manufacturer_inactive: bool = False

    @property
    def created(self) -> int:
        """Number of chassis created."""
        return sum(1 for entry in self.ingested if entry.outcome == "created")

    @property
    def updated(self) -> int:
        """Number of existing chassis updated or moved."""
        return sum(1 for entry in self.ingested if entry.outcome == "updated")


class ChassisIngestService:
    """The one place that turns normalized chassis into persisted chassis."""

    @classmethod
    def ingest(
        cls,
        payloads: Sequence[NormalizedChassis],
        *,
        manufacturer: Manufacturer,
        mode: IngestMode,
        require_active: bool = True,
    ) -> ChassisIngestResult:
        """Persist payloads under the global identity lock and report each outcome.

        One payload that cannot be persisted is counted in `failed` and does not stop the
        rest. An authoritative snapshot only marks absent chassis offline when every payload
        was persisted or deliberately skipped, so a partial failure never reads as an outage.
        With `require_active`, a manufacturer deactivated before the lock was taken ingests
        nothing.
        """
        result = ChassisIngestResult()
        with DeviceIdentityMutationLockService.acquire(
            manufacturer=manufacturer
        ) as locked_manufacturer:
            if require_active and not locked_manufacturer.is_active:
                logger.info(
                    "Chassis ingest stopped after deactivation for manufacturer ID %s",
                    locked_manufacturer.pk,
                )
                result.manufacturer_inactive = True
                return result

            identity_index = DeviceIdentityIndex.build(payloads, manufacturer=locked_manufacturer)
            with coalesce_discovery_scheduling():
                for position, payload in enumerate(payloads, start=1):
                    try:
                        with transaction.atomic():
                            entry = cls._ingest_one(payload, locked_manufacturer, identity_index)
                    except Exception as exc:
                        result.failed += 1
                        logger.exception(
                            "Error ingesting vendor device at snapshot position %s",
                            position,
                            exc_info=sanitized_exception_info(exc),
                        )
                        continue
                    if entry is not None:
                        result.ingested.append(entry)

        if mode is IngestMode.AUTHORITATIVE_SNAPSHOT:
            if result.failed:
                logger.warning(
                    "Skipped offline reconciliation for %s because the snapshot was incomplete",
                    manufacturer.code,
                )
            else:
                cls._mark_absent_offline(
                    manufacturer=manufacturer,
                    present_ids=[entry.chassis.pk for entry in result.ingested],
                )
        return result

    @classmethod
    def _ingest_one(
        cls,
        payload: NormalizedChassis,
        manufacturer: Manufacturer,
        identity_index: DeviceIdentityIndex,
    ) -> IngestedChassis | None:
        """Persist one payload, or return None when it is skipped."""
        payload = cls._with_known_address(payload, manufacturer, identity_index)
        if not payload.ip:
            logger.debug(
                "Skipped chassis ingest for manufacturer ID %s: no address to create from",
                manufacturer.pk,
            )
            return None

        dedup_result = check_device(
            serial_number=payload.serial_number or None,
            mac_address=canonicalize_mac_address(payload.mac_address) or None,
            ip=payload.ip,
            api_device_id=payload.api_device_id,
            manufacturer=manufacturer,
            identity_index=identity_index,
        )
        if dedup_result.is_conflict:
            return None

        existing = dedup_result.existing_device
        if existing is not None and existing.manufacturer_id != manufacturer.pk:
            logger.warning(
                "Rejected cross-manufacturer ingest candidate "
                "(device_id=%s, existing_manufacturer_id=%s, new_manufacturer_id=%s)",
                existing.pk,
                existing.manufacturer_id,
                manufacturer.pk,
            )
            return None

        if existing is not None and dedup_result.is_moved:
            cls._persist_move(existing, payload, identity_index)
            return IngestedChassis(payload, existing, "updated")

        if existing is not None and dedup_result.is_duplicate:
            WirelessChassisPersistenceService.update_from_normalized(
                chassis=existing,
                payload=payload,
            )
            cls._bring_online(existing)
            return IngestedChassis(payload, existing, "updated")

        if dedup_result.is_new:
            chassis = WirelessChassisPersistenceService.create_from_normalized(
                payload=payload,
                manufacturer=manufacturer,
                initial_status=HardwareStatus.ONLINE,
            )
            identity_index.add(chassis)
            logger.info(
                "Created wireless chassis %s for manufacturer %s",
                chassis.pk,
                manufacturer.pk,
            )
            return IngestedChassis(payload, chassis, "created")
        return None

    @staticmethod
    def _with_known_address(
        payload: NormalizedChassis,
        manufacturer: Manufacturer,
        identity_index: DeviceIdentityIndex,
    ) -> NormalizedChassis:
        """Give an address-less event the address of the chassis its API id already names."""
        if payload.ip:
            return payload
        known = identity_index.api_id(manufacturer.pk, payload.api_device_id)
        if known is None:
            return payload
        return payload.model_copy(update={"ip": str(known.ip)})

    @classmethod
    def _persist_move(
        cls,
        chassis: WirelessChassis,
        payload: NormalizedChassis,
        identity_index: DeviceIdentityIndex,
    ) -> None:
        """Persist an address move and keep the batch identity index current."""
        old_ip = str(chassis.ip) if chassis.ip else None
        WirelessChassisPersistenceService.update_from_normalized(
            chassis=chassis,
            payload=payload,
            set_ip=True,
        )
        new_ip = str(chassis.ip) if chassis.ip else None
        if old_ip != new_ip:
            log_device_movement(
                device=chassis,
                old_ip=old_ip,
                new_ip=new_ip,
                detected_by="chassis_ingest",
                reason="Chassis ingest detected an address change",
            )
        if old_ip is not None:
            identity_index.move_ip(chassis, old_ip=old_ip)
        cls._bring_online(chassis)

    @staticmethod
    def _bring_online(chassis: WirelessChassis) -> None:
        """Let the lifecycle decide what a responding device means for its status."""
        HardwareLifecycleManager().bring_responding_online(
            chassis, reason="Device responding during chassis ingest"
        )

    @staticmethod
    def _mark_absent_offline(
        *,
        manufacturer: Manufacturer,
        present_ids: Sequence[int],
    ) -> None:
        """Mark chassis missing from an authoritative snapshot offline and raise their alerts."""
        absent = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status__in={"online", "degraded", "provisioning"},
        ).exclude(id__in=present_ids)
        lifecycle = HardwareLifecycleManager()
        marked: list[int] = []
        for chassis in absent:
            try:
                lifecycle.mark_offline(chassis, reason="Device not found in API poll")
                marked.append(chassis.pk)
            except Exception as exc:
                logger.exception(
                    "Error marking wireless chassis %s offline",
                    chassis.pk,
                    exc_info=sanitized_exception_info(exc),
                )
        if not marked:
            return
        logger.warning(
            "Marked %d chassis offline for manufacturer %s",
            len(marked),
            manufacturer.pk,
        )
        offline = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status="offline",
        ).prefetch_related("field_units")
        for chassis in offline:
            for unit in chassis.field_units.all():
                alert_manager.check_hardware_offline_alerts(unit)
