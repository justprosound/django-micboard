"""Tenant route resolution for realtime event producers."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings

from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

GLOBAL_UPDATES_GROUP = "micboard_updates"
GLOBAL_UPDATES_PERMISSION = "micboard.view_realtimeconnection"
TenantScope = tuple[int, int | None]


def organization_updates_group(organization_id: int) -> str:
    """Return the realtime group for organization-wide updates."""
    return f"{GLOBAL_UPDATES_GROUP}.organization.{organization_id}"


def campus_updates_group(organization_id: int, campus_id: int) -> str:
    """Return the realtime group for updates restricted to one campus."""
    return f"{organization_updates_group(organization_id)}.campus.{campus_id}"


def site_updates_group(site_id: int) -> str:
    """Return the realtime group for one Django Site."""
    return f"{GLOBAL_UPDATES_GROUP}.site.{site_id}"


class RealtimeRoutingService:
    """Resolve tenant-safe group names and model ownership."""

    @staticmethod
    def can_receive_global_updates(user: Any) -> bool:
        """Return whether a user may subscribe to the unpartitioned event stream."""
        return bool(getattr(user, "is_active", False) and user.has_perm(GLOBAL_UPDATES_PERMISSION))

    @staticmethod
    def normalize_identifier(value: Any) -> int | None:
        """Return a positive integer identifier or ``None``."""
        try:
            identifier = int(value)
        except (TypeError, ValueError):
            return None
        return identifier if identifier > 0 else None

    @classmethod
    def scope_from_mapping(cls, data: Mapping[str, Any]) -> TenantScope | None:
        """Extract a valid tenant scope from serialized event data."""
        organization_id = cls.normalize_identifier(data.get("organization_id"))
        if organization_id is None:
            return None
        return organization_id, cls.normalize_identifier(data.get("campus_id"))

    @classmethod
    def groups_for_scope(
        cls,
        *,
        organization_id: int | None = None,
        campus_id: int | None = None,
        site_id: int | None = None,
    ) -> tuple[str, ...]:
        """Return global or tenant groups for one event scope.

        Campus events also go to the parent organization group so organization-wide
        members retain visibility into their complete estate.
        """
        if not micboard_settings.msp_enabled:
            if not micboard_settings.multi_site_mode:
                return (GLOBAL_UPDATES_GROUP,)
            resolved_site_id = site_id or cls.normalize_identifier(
                getattr(settings, "SITE_ID", None)
            )
            return (site_updates_group(resolved_site_id),) if resolved_site_id else ()
        if organization_id is None:
            return ()

        groups = [organization_updates_group(organization_id)]
        if campus_id is not None:
            groups.append(campus_updates_group(organization_id, campus_id))
        return tuple(groups)

    @staticmethod
    def chassis_site_ids(chassis_ids: Iterable[int]) -> dict[int, int]:
        """Resolve chassis IDs to Django Site IDs in one query."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        try:
            rows = WirelessChassis._default_manager.filter(pk__in=set(chassis_ids)).values_list(
                "pk",
                "location__building__site_id",
            )
            return {device_id: site_id for device_id, site_id in rows if site_id is not None}
        except Exception as exc:
            logger.exception(
                "Failed to resolve chassis site routes",
                exc_info=sanitized_exception_info(exc),
            )
            return {}

    @staticmethod
    def chassis_tenant_scopes(chassis_ids: Iterable[int]) -> dict[int, TenantScope]:
        """Resolve chassis IDs to their building tenant scopes in one query."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        try:
            rows = WirelessChassis._default_manager.filter(pk__in=set(chassis_ids)).values_list(
                "pk",
                "location__building__organization_id",
                "location__building__campus_id",
            )
            return {
                device_id: (organization_id, campus_id)
                for device_id, organization_id, campus_id in rows
                if organization_id is not None
            }
        except Exception as exc:
            logger.exception(
                "Failed to resolve chassis tenant routes",
                exc_info=sanitized_exception_info(exc),
            )
            return {}

    @classmethod
    def hardware_tenant_scope(
        cls,
        *,
        device_type: str,
        device_id: int,
    ) -> TenantScope | None:
        """Resolve a supported hardware model ID without cross-model ambiguity."""
        if device_type == "WirelessChassis":
            return cls.chassis_tenant_scopes((device_id,)).get(device_id)
        if device_type != "WirelessUnit":
            logger.warning("Skipped realtime route for unknown device type: %s", device_type)
            return None

        from micboard.models.hardware.wireless_unit import WirelessUnit

        try:
            row = (
                WirelessUnit._default_manager.filter(pk=device_id)
                .values_list(
                    "base_chassis__location__building__organization_id",
                    "base_chassis__location__building__campus_id",
                )
                .first()
            )
        except Exception as exc:
            logger.exception(
                "Failed to resolve wireless unit tenant route",
                exc_info=sanitized_exception_info(exc),
            )
            return None

        if row is None or row[0] is None:
            return None
        return row[0], row[1]

    @classmethod
    def hardware_site_id(cls, *, device_type: str, device_id: int) -> int | None:
        """Resolve a supported hardware model ID to its Django Site."""
        if device_type == "WirelessChassis":
            return cls.chassis_site_ids((device_id,)).get(device_id)
        if device_type != "WirelessUnit":
            logger.warning("Skipped realtime route for unknown device type: %s", device_type)
            return None

        from micboard.models.hardware.wireless_unit import WirelessUnit

        try:
            return (
                WirelessUnit._default_manager.filter(pk=device_id)
                .values_list("base_chassis__location__building__site_id", flat=True)
                .first()
            )
        except Exception as exc:
            logger.exception(
                "Failed to resolve wireless unit site route",
                exc_info=sanitized_exception_info(exc),
            )
            return None

    @staticmethod
    def manufacturer_tenant_scopes(manufacturer: Any) -> tuple[TenantScope, ...]:
        """Resolve tenants that own chassis for a manufacturer."""
        manufacturer_id = getattr(manufacturer, "pk", None)
        if manufacturer_id is None:
            return ()

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        try:
            rows = (
                WirelessChassis._default_manager.filter(
                    manufacturer_id=manufacturer_id,
                    location__building__organization_id__isnull=False,
                )
                .values_list(
                    "location__building__organization_id",
                    "location__building__campus_id",
                )
                .distinct()
            )
            return tuple(
                (organization_id, campus_id)
                for organization_id, campus_id in rows
                if organization_id is not None
            )
        except Exception as exc:
            logger.exception(
                "Failed to resolve manufacturer tenant routes",
                exc_info=sanitized_exception_info(exc),
            )
            return ()

    @staticmethod
    def manufacturer_site_ids(manufacturer: Any) -> tuple[int, ...]:
        """Resolve sites that own chassis for a manufacturer."""
        manufacturer_id = getattr(manufacturer, "pk", None)
        if manufacturer_id is None:
            return ()

        from micboard.models.hardware.wireless_chassis import WirelessChassis

        try:
            return tuple(
                WirelessChassis._default_manager.filter(
                    manufacturer_id=manufacturer_id,
                    location__building__site_id__isnull=False,
                )
                .values_list("location__building__site_id", flat=True)
                .distinct()
            )
        except Exception as exc:
            logger.exception(
                "Failed to resolve manufacturer site routes",
                exc_info=sanitized_exception_info(exc),
            )
            return ()
