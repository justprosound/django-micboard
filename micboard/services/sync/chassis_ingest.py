"""Identity-safe ingest of normalized chassis from every source.

The poll, realtime and API-server paths all persist what a manufacturer reported through
`ChassisIngestService.ingest`, so a chassis already known under another identity (serial,
MAC, address or API id) is matched, moved or rejected the same way whichever path saw it.
"""

import logging
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from django.db import transaction

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware_lifecycle import (
    RESPONDING_STATUSES,
    HardwareLifecycleManager,
    HardwareStatus,
)
from micboard.services.deduplication.check import check_device
from micboard.services.deduplication.identity_index import DeviceIdentityIndex
from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
)
from micboard.services.deduplication.tracking import log_device_movement
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.services.monitoring.alerts import ChassisOfflineNotice, alert_manager
from micboard.services.sync.chassis_normalization import ChassisNormalizer, normalize_batch
from micboard.services.sync.chassis_payload_identity import named_chassis_ids, with_known_address
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


@dataclass(frozen=True, slots=True)
class _NotPersisted:
    """A payload ingest declined, and the chassis of this manufacturer it still names."""

    kind: Literal["skipped", "rejected"]
    named_chassis_ids: frozenset[int] = frozenset()


@dataclass(slots=True)
class ChassisIngestResult:
    """What one ingest persisted, skipped, rejected and failed.

    `unnormalizable` counts raw devices the plugin could not read; `skipped` counts payloads
    with no address to create from, `unidentified` of them naming no chassis of this
    manufacturer; `rejected` counts payloads refused for an identity conflict or because
    another manufacturer owns the chassis.
    """

    ingested: list[IngestedChassis] = field(default_factory=list)
    failed: int = 0
    unnormalizable: int = 0
    skipped: int = 0
    unidentified: int = 0
    rejected: int = 0
    manufacturer_inactive: bool = False
    marked_offline: int = 0

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
        raw_devices: Iterable[Mapping[str, Any]],
        *,
        plugin: ChassisNormalizer,
        manufacturer: Manufacturer,
        mode: IngestMode,
        require_active: bool = True,
    ) -> ChassisIngestResult:
        """Normalize raw vendor payloads once, persist them and report each outcome.

        Poll, realtime and API-server updates all enter here and differ only in `mode`.
        An address-less payload takes the address of the chassis its API id names, or is
        skipped. One payload that cannot be persisted is counted in `failed` and does not
        stop the rest. An authoritative snapshot only marks absent chassis offline when
        at least one device was read and every one was read: none failed, none could not be normalized, and none was
        skipped without naming a chassis, because such a device might be the one that
        looks absent. It never marks a chassis that a skipped or rejected payload still
        names, so neither a partial failure nor a refused payload reads as an outage.
        With `require_active`, a manufacturer deactivated before the lock was taken ingests
        nothing.
        """
        batch = normalize_batch(raw_devices, plugin)
        payloads = batch.payloads
        result = ChassisIngestResult(unnormalizable=batch.unnormalizable)
        protected_ids: set[int] = set()
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
                    if isinstance(entry, IngestedChassis):
                        result.ingested.append(entry)
                        continue
                    if entry.kind == "skipped":
                        result.skipped += 1
                        if not entry.named_chassis_ids:
                            result.unidentified += 1
                    else:
                        result.rejected += 1
                    protected_ids.update(entry.named_chassis_ids)

        if mode is IngestMode.AUTHORITATIVE_SNAPSHOT:
            unread = result.failed + result.unnormalizable + result.unidentified
            if not payloads and not unread:
                logger.warning(
                    "Skipped offline reconciliation for manufacturer %s because no device was read",
                    manufacturer.pk,
                )
            elif unread:
                logger.warning(
                    "Skipped offline reconciliation for manufacturer %s because %d device(s) "
                    "were not fully read",
                    manufacturer.pk,
                    unread,
                )
            else:
                result.marked_offline = cls._mark_absent_offline(
                    manufacturer=manufacturer,
                    present_ids={entry.chassis.pk for entry in result.ingested} | protected_ids,
                )
        return result

    @classmethod
    def _ingest_one(
        cls,
        payload: NormalizedChassis,
        manufacturer: Manufacturer,
        identity_index: DeviceIdentityIndex,
    ) -> IngestedChassis | _NotPersisted:
        """Persist one payload, or say why it was not."""
        payload = with_known_address(payload, manufacturer, identity_index)
        named = named_chassis_ids(payload, manufacturer, identity_index)
        if not payload.ip:
            logger.debug(
                "Skipped chassis ingest for manufacturer ID %s: no address to create from",
                manufacturer.pk,
            )
            return _NotPersisted("skipped", named)

        dedup_result = check_device(
            serial_number=payload.serial_number or None,
            mac_address=canonicalize_mac_address(payload.mac_address) or None,
            ip=payload.ip,
            api_device_id=payload.api_device_id,
            manufacturer=manufacturer,
            identity_index=identity_index,
        )
        if dedup_result.is_conflict:
            return _NotPersisted("rejected", named)

        existing = dedup_result.existing_device
        if existing is not None and existing.manufacturer_id != manufacturer.pk:
            logger.warning(
                "Rejected cross-manufacturer ingest candidate "
                "(device_id=%s, existing_manufacturer_id=%s, new_manufacturer_id=%s)",
                existing.pk,
                existing.manufacturer_id,
                manufacturer.pk,
            )
            return _NotPersisted("rejected", named)

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
        return _NotPersisted("rejected", named)

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
        cls._bring_online(chassis)
        if old_ip is not None:
            identity_index.move_ip(chassis, old_ip=old_ip)

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
        present_ids: Collection[int],
    ) -> int:
        """Mark chassis missing from an authoritative snapshot offline and raise their alerts.

        Returns the number of chassis marked offline.
        """
        absent_ids = list(
            WirelessChassis.objects.filter(
                manufacturer=manufacturer,
                status__in=RESPONDING_STATUSES,
            )
            .exclude(id__in=present_ids)
            .values_list("pk", flat=True)
        )
        lifecycle = HardwareLifecycleManager()
        notices: dict[int, ChassisOfflineNotice] = {}
        for chassis_id in absent_ids:
            try:
                with transaction.atomic():
                    # Read under the row lock, so a concurrent update cannot leave the times
                    # stale. The offline transition stamps `last_seen`, so read them first.
                    chassis = WirelessChassis.objects.select_for_update().get(pk=chassis_id)
                    notice = ChassisOfflineNotice(
                        last_seen=chassis.last_seen, last_online_at=chassis.last_online_at
                    )
                    transitioned = chassis.status in RESPONDING_STATUSES and lifecycle.mark_offline(
                        chassis, reason="Device not found in API poll"
                    )
            except Exception as exc:
                logger.exception(
                    "Error marking wireless chassis %s offline",
                    chassis_id,
                    exc_info=sanitized_exception_info(exc),
                )
                continue
            if not transitioned:
                continue
            notices[chassis_id] = notice
            logger.warning(
                "Wireless chassis %s absent from the complete inventory of manufacturer %s, "
                "marked offline (%s)",
                chassis_id,
                manufacturer.pk,
                notice.describe(),
                extra={
                    "event.action": "chassis_offline",
                    "micboard.chassis.id": chassis_id,
                    "micboard.chassis.last_seen": _iso(notice.last_seen),
                    "micboard.chassis.last_online_at": _iso(notice.last_online_at),
                },
            )
        if not notices:
            return 0
        budget = AlertFanoutBudget.from_settings()
        offline = WirelessChassis.objects.filter(pk__in=notices).prefetch_related("field_units")
        for chassis in offline:
            for unit in chassis.field_units.all():
                alert_manager.check_hardware_offline_alerts(
                    unit, budget=budget, chassis_offline=notices[chassis.pk]
                )
        return len(notices)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None
