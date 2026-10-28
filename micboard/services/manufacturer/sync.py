"""Device synchronization operations for manufacturers.

Writes device data from manufacturer APIs to the local database,
handling normalization, deduplication, chassis creation and updates.
"""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from micboard.services.common.base.plugin import build_manufacturer_plugin
from micboard.services.sync.chassis_ingest import ChassisIngestService, IngestMode
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
                statuses=["online", "degraded", "provisioning"],
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
        if not result.errors:
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

            normalized_devices = ManufacturerSyncService._normalize_devices(
                inventory.devices,
                plugin,
            )

            if not normalized_devices:
                return ManufacturerSyncResult(
                    success=True,
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                )

            # A poll never reconciles absent chassis today, so it ingests as a partial inventory.
            ingest = ChassisIngestService.ingest(
                normalized_devices,
                manufacturer=manufacturer,
                mode=IngestMode.PARTIAL_EVENT,
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

            return ManufacturerSyncResult(
                success=not ingest.failed,
                errors=(
                    [
                        f"Device synchronization failed for {ingest.failed} device(s); details redacted."
                    ]
                    if ingest.failed
                    else []
                ),
                devices_added=ingest.created,
                devices_updated=ingest.updated,
                devices_examined=len(inventory.devices),
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
    def _normalize_devices(
        api_devices: Iterable[dict[str, Any]], plugin: DeviceUpdatePlugin
    ) -> list[NormalizedChassis]:
        """Normalize raw API device payloads, keeping only devices with an address."""
        normalized: list[NormalizedChassis] = []
        for raw in api_devices:
            payload = plugin.normalize_device(raw)
            if payload is not None and payload.ip:
                normalized.append(payload)
        return normalized
