"""Reusable mixins for Django models to reduce code duplication."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class DiscoveryTriggerMixin:
    """Mixin for models that should trigger discovery scans when saved/deleted.

    Used by MicboardConfiguration, DiscoveryCIDR, DiscoveryFQDN, and Manufacturer
    to trigger async discovery tasks.
    """

    manufacturer_id: int | None  # Should be implemented by subclass

    def _trigger_discovery(self, manufacturer_pk: int | None = None) -> None:
        """Trigger async discovery scan for a manufacturer (delegates to service)."""
        pk = manufacturer_pk or self.manufacturer_id
        from micboard.services.sync.discovery_trigger_service import trigger_discovery

        trigger_discovery(pk)


class TenantFilterableMixin(models.QuerySet):
    """QuerySet mixin for applying MSP/multi-site tenant filtering.

    Handles filtering based on MICBOARD_MSP_ENABLED and MICBOARD_MULTI_SITE_MODE settings.
    """

    def apply_tenant_filters(
        self,
        organization_id: int | None = None,
        campus_id: int | None = None,
        site_id: int | None = None,
        building_path: str = "location__building",
    ) -> TenantFilterableMixin:
        """Apply tenant/site filtering based on configured mode.

        Args:
            organization_id: Organization ID (for MSP mode).
            campus_id: Campus ID (for MSP mode).
            site_id: Site ID (for multi-site mode).
            building_path: Path to building field (e.g., 'location__building', 'base_chassis__location__building').

        Returns:
            Filtered QuerySet.
        """
        qs = self

        if getattr(settings, "MICBOARD_MSP_ENABLED", False):
            # MSP mode: filter by organization or campus
            if organization_id:
                qs = qs.filter(**{f"{building_path}__organization_id": organization_id})
            if campus_id:
                qs = qs.filter(**{f"{building_path}__campus_id": campus_id})
        elif getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            # Multi-site mode: filter by site
            if site_id:
                qs = qs.filter(**{f"{building_path}__site_id": site_id})

        return qs
