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
        """Trigger async discovery scan for a manufacturer.

        Args:
            manufacturer_pk: Manufacturer PK to scan. If None, uses self.manufacturer_id.
        """
        from micboard.utils.dependencies import HAS_DJANGO_Q

        if not HAS_DJANGO_Q:
            logger.debug("django-q not available, skipping discovery trigger")
            return

        pk = manufacturer_pk or self.manufacturer_id
        if not pk:
            logger.warning("No manufacturer_id available for discovery trigger")
            return

        try:
            from django_q.tasks import async_task

            from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

            async_task(
                run_manufacturer_discovery_task,
                pk,
                True,  # scan_cidrs
                True,  # scan_fqdns
            )
            logger.info(f"Triggered discovery scan for manufacturer {pk}")
        except Exception as e:
            logger.warning(f"Failed to trigger discovery scan: {e}")


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


class AuditableModelMixin(models.Model):
    """Abstract mixin for models with audit logging on save/delete.

    Subclasses should call _log_change() or _log_delete() to record changes.
    """

    class Meta:
        abstract = True

    def _log_change(self, action: str = "modified") -> None:
        """Log model change to audit log.

        Args:
            action: Type of action ('created', 'modified', 'deleted').
        """
        logger.info(
            f"{self.__class__.__name__} {action}: {self}",
            extra={"model": self.__class__.__name__, "action": action, "pk": self.pk},
        )

    def clean_and_validate(self) -> None:
        """Call full_clean() and raise ValidationError if invalid.

        Override in subclass to add custom validation.
        """
        self.full_clean()
