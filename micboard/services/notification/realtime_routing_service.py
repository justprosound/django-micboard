"""Tenant route resolution for realtime event producers."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

GLOBAL_UPDATES_GROUP = "micboard_updates"
TenantScope = tuple[int, int | None]


def organization_updates_group(organization_id: int) -> str:
    """Return the realtime group for organization-wide updates."""
    return f"{GLOBAL_UPDATES_GROUP}.organization.{organization_id}"


def campus_updates_group(organization_id: int, campus_id: int) -> str:
    """Return the realtime group for updates restricted to one campus."""
    return f"{organization_updates_group(organization_id)}.campus.{campus_id}"


class RealtimeRoutingService:
    """Resolve tenant-safe group names and model ownership."""

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

    @staticmethod
    def groups_for_scope(
        *, organization_id: int | None = None, campus_id: int | None = None
    ) -> tuple[str, ...]:
        """Return global or tenant groups for one event scope.

        Campus events also go to the parent organization group so organization-wide
        members retain visibility into their complete estate.
        """
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return (GLOBAL_UPDATES_GROUP,)
        if organization_id is None:
            return ()

        groups = [organization_updates_group(organization_id)]
        if campus_id is not None:
            groups.append(campus_updates_group(organization_id, campus_id))
        return tuple(groups)

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
        except Exception:
            logger.exception("Failed to resolve chassis tenant routes")
            return {}

    @classmethod
    def chassis_tenant_scope(cls, chassis_id: int) -> TenantScope | None:
        """Resolve one chassis ID to its building tenant scope."""
        return cls.chassis_tenant_scopes((chassis_id,)).get(chassis_id)

    @classmethod
    def hardware_tenant_scope(
        cls,
        *,
        device_type: str,
        device_id: int,
    ) -> TenantScope | None:
        """Resolve a supported hardware model ID without cross-model ambiguity."""
        if device_type == "WirelessChassis":
            return cls.chassis_tenant_scope(device_id)
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
        except Exception:
            logger.exception("Failed to resolve wireless unit tenant route")
            return None

        if row is None or row[0] is None:
            return None
        return row[0], row[1]

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
        except Exception:
            logger.exception("Failed to resolve manufacturer tenant routes")
            return ()
