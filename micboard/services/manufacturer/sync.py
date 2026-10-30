"""Device synchronization operations for manufacturers.

Writes device data from manufacturer APIs to the local database,
handling normalization, deduplication, chassis creation and updates.
"""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from micboard.services.common.base.plugin import build_manufacturer_plugin
from micboard.services.core.hardware_lifecycle import RESPONDING_STATUSES
from micboard.services.sync.chassis_ingest import (
    ChassisIngestResult,
    ChassisIngestService,
    IngestMode,
)
from micboard.services.sync.device_update_service import DeviceUpdatePlugin
from micboard.services.sync.polling_dtos import (
    ManufacturerPollLimits,
    ManufacturerSyncResult,
    VendorInventoryBatch,
)
from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.services.core.hardware import NormalizedChassis

logger = logging.getLogger(__name__)


class ManufacturerSyncService:
    """Write operations for manufacturer device synchronization."""

    @staticmethod
    def _record_poll_audit(
        *,
        manufacturer: Manufacturer,
        started_at: datetime,
        result: ManufacturerSyncResult,
    ) -> None:
        """Delegate bounded audit persistence without widening this interface."""
        from micboard.services.maintenance.sync_audit_service import ServiceSyncAuditService

        ServiceSyncAuditService.record_poll_result(
            manufacturer=manufacturer,
            started_at=started_at,
            result=result,
        )

    @staticmethod
    def _broadcast_persisted_devices(manufacturer: Manufacturer) -> None:
        """Publish the persisted snapshot, containing broadcast failures."""
        from micboard.services.notification.device_broadcast_service import (
            DeviceSnapshotBroadcastService,
        )
        from micboard.services.sync.polling_dtos import ManufacturerPollLimits

        try:
            limits = ManufacturerPollLimits.from_settings()
            DeviceSnapshotBroadcastService.broadcast(
                manufacturer=manufacturer,
                namespace="poll",
                max_devices=limits.max_devices,
                chunk_size=limits.broadcast_chunk_size,
                statuses=sorted(RESPONDING_STATUSES),
            )
        except Exception as exc:
            logger.exception(
                "Failed to broadcast device updates for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @staticmethod
    def sync_devices_for_manufacturer(
        *,
        manufacturer_code: str,
        organization_id: int | None = None,
        campus_id: int | None = None,
        force: bool = False,
    ) -> ManufacturerSyncResult:
        """Poll one manufacturer, persist its inventory, audit the run, and broadcast it.

        One poll has one outcome: the returned DTO is what operators, background tasks, and
        the audit trail all read, so their counts cannot disagree.
        """
        from django.utils import timezone

        from micboard.models.discovery.manufacturer import Manufacturer

        started_at = timezone.now()
        result = ManufacturerSyncService._sync_inventory(
            manufacturer_code=manufacturer_code,
            organization_id=organization_id,
            campus_id=campus_id,
            force=force,
        )

        # Reload by code alone: `_sync_inventory` has already applied the activation policy
        # and reported a failure if it was not met, and a manufacturer that deactivated during
        # vendor I/O still needs the poll recorded against it.
        manufacturer = Manufacturer.objects.filter(code=manufacturer_code).first()
        if manufacturer is None:
            return result

        ManufacturerSyncService._record_poll_audit(
            manufacturer=manufacturer,
            started_at=started_at,
            result=result,
        )
        # Rows that committed are worth publishing even when another device in the same poll
        # failed, so one persistently bad device cannot silence every other one.
        if result.devices_added or result.devices_updated:
            ManufacturerSyncService._broadcast_persisted_devices(manufacturer)
        return result

    @staticmethod
    def _sync_inventory(
        *,
        manufacturer_code: str,
        organization_id: int | None = None,
        campus_id: int | None = None,
        force: bool = False,
    ) -> ManufacturerSyncResult:
        """Synchronize all devices from a manufacturer.

        Polls the manufacturer API and updates local models.

        Args:
            manufacturer_code: Manufacturer code.
            organization_id: Optional organization ID for MSP mode.
            campus_id: Optional campus ID for MSP mode.
            force: Permit an explicitly requested operator poll while inactive.

        Returns:
            A validated `ManufacturerSyncResult`. Read `success` before its counts: an
            expected failure is reported there rather than raised. `devices_added`,
            `devices_updated`, `devices_removed` and `devices_examined` describe chassis,
            not wireless units, and `errors` carries the redacted failure messages.
        """
        from micboard.models.discovery.manufacturer import Manufacturer

        limits = ManufacturerPollLimits.from_settings()

        manufacturer_filters: dict[str, str | bool] = {"code": manufacturer_code}
        if not force:
            manufacturer_filters["is_active"] = True
        try:
            manufacturer = Manufacturer.objects.get(**manufacturer_filters)
        except Manufacturer.DoesNotExist:
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Manufacturer not found or inactive: {manufacturer_code}"],
                device_limit=limits.max_devices,
            )

        try:
            plugin = build_manufacturer_plugin(manufacturer)
        except ImportError:
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Plugin not found: {manufacturer_code}"],
                device_limit=limits.max_devices,
            )
        except Exception as exc:
            # A vendor constructor reads host configuration and can fail for reasons that are
            # not a missing integration. Reporting those as "not found" would send an operator
            # looking for the wrong problem, and letting them escape would skip the audit.
            logger.exception(
                "Manufacturer plugin initialization failed for %s",
                manufacturer_code,
                exc_info=sanitized_exception_info(exc),
            )
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Plugin initialization failed ({type(exc).__name__}); details redacted."],
                device_limit=limits.max_devices,
            )

        try:
            api_devices = plugin.get_devices() or ()
            # A client that dropped part of the response says so on the list it returns.
            source_complete = getattr(api_devices, "complete", True)
            inventory = VendorInventoryBatch.consume(
                api_devices,
                device_limit=limits.max_devices,
            )
            if not inventory.inventory_complete:
                return ManufacturerSyncResult(
                    success=False,
                    errors=[
                        "Manufacturer inventory exceeded the configured device limit; "
                        "no devices were synchronized."
                    ],
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                    inventory_complete=False,
                )

            normalized_devices, unnormalizable, unaddressed = (
                ManufacturerSyncService._normalize_devices(inventory.devices, plugin)
            )

            if not normalized_devices:
                return ManufacturerSyncService._ingest_outcome(
                    None,
                    examined=len(inventory.devices),
                    unnormalizable=unnormalizable,
                    unaddressed=unaddressed,
                    device_limit=limits.max_devices,
                )

            ingest = ChassisIngestService.ingest(
                normalized_devices,
                manufacturer=manufacturer,
                mode=ManufacturerSyncService._ingest_mode(
                    manufacturer,
                    source_complete=source_complete,
                    unnormalizable=unnormalizable,
                    unaddressed=unaddressed,
                ),
                require_active=not force,
            )
            if ingest.manufacturer_inactive:
                return ManufacturerSyncResult(
                    success=False,
                    errors=[
                        "Manufacturer became inactive during polling; no devices were synchronized."
                    ],
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                )

            return ManufacturerSyncService._ingest_outcome(
                ingest,
                examined=len(inventory.devices),
                unnormalizable=unnormalizable,
                unaddressed=unaddressed,
                device_limit=limits.max_devices,
            )

        except Exception as exc:
            logger.exception(
                "Manufacturer device synchronization failed for %s",
                manufacturer_code,
                exc_info=sanitized_exception_info(exc),
            )
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Device synchronization failed ({type(exc).__name__}); details redacted."],
                device_limit=limits.max_devices,
            )

    @staticmethod
    def _ingest_mode(
        manufacturer: Manufacturer,
        *,
        source_complete: bool,
        unnormalizable: int,
        unaddressed: int,
    ) -> IngestMode:
        """Reconcile absent chassis only when the poll read the vendor's whole inventory.

        A fetch that failed raised before this point, a truncated one was refused, and an
        empty one never reaches ingest. What is left is a complete inventory unless the
        client dropped part of the response or a device was dropped before ingest: its
        identity is unknown, so it might be the chassis that looks absent.
        """
        if not source_complete or unnormalizable or unaddressed:
            logger.warning(
                "Skipped offline reconciliation for manufacturer %s because the inventory "
                "was not fully read (%d device(s) dropped before ingest)",
                manufacturer.pk,
                unnormalizable + unaddressed,
            )
            return IngestMode.PARTIAL_EVENT
        return IngestMode.AUTHORITATIVE_SNAPSHOT

    @staticmethod
    def _ingest_outcome(
        ingest: ChassisIngestResult | None,
        *,
        examined: int,
        unnormalizable: int,
        unaddressed: int,
        device_limit: int,
    ) -> ManufacturerSyncResult:
        """Report every examined device as persisted, skipped, rejected or failed."""
        created = updated = failed = rejected = ingest_skipped = removed = 0
        if ingest is not None:
            created, updated = ingest.created, ingest.updated
            removed = ingest.marked_offline
            failed, rejected, ingest_skipped = ingest.failed, ingest.rejected, ingest.skipped
        skipped = ingest_skipped + unnormalizable + unaddressed
        errors: list[str] = []
        if failed:
            errors.append(
                f"Device synchronization failed for {failed} device(s); details redacted."
            )
        if rejected:
            errors.append(f"{rejected} device(s) were rejected for an identity conflict.")
        if unnormalizable:
            errors.append(f"{unnormalizable} device(s) were skipped for failing normalization.")
        if unaddressed:
            errors.append(f"{unaddressed} device(s) were skipped for lacking an address.")
        if ingest_skipped:
            errors.append(f"{ingest_skipped} device(s) were skipped during ingest.")
        return ManufacturerSyncResult(
            success=not errors,
            errors=errors,
            devices_added=created,
            devices_updated=updated,
            devices_removed=removed,
            devices_skipped=skipped,
            devices_rejected=rejected,
            devices_examined=examined,
            device_limit=device_limit,
        )

    @staticmethod
    def _normalize_devices(
        api_devices: Iterable[dict[str, Any]], plugin: DeviceUpdatePlugin
    ) -> tuple[list[NormalizedChassis], int, int]:
        """Normalize raw payloads, keeping addressed devices and counting both drop causes.

        Returns the addressed devices, the count that failed normalization and the count
        that normalized without an address.
        """
        normalized: list[NormalizedChassis] = []
        unnormalizable = unaddressed = 0
        for raw in api_devices:
            payload = plugin.normalize_device(raw)
            if payload is None:
                unnormalizable += 1
            elif not payload.ip:
                unaddressed += 1
            else:
                normalized.append(payload)
        return normalized, unnormalizable, unaddressed
