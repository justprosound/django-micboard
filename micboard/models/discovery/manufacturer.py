"""Manufacturer model for device vendor registry."""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models

from micboard.models.audit import ActivityLog

logger = logging.getLogger(__name__)


class Manufacturer(models.Model):
    """Represents a device manufacturer with audit logging."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Manufacturer name (e.g., 'Shure', 'Sennheiser')",
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Short code for the manufacturer (e.g., 'shure', 'sennheiser')",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this manufacturer is currently supported",
    )
    config = models.JSONField(
        default=dict,
        help_text="Manufacturer-specific configuration",
    )

    class Meta:
        verbose_name = "Manufacturer"
        verbose_name_plural = "Manufacturers"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def _log_change(self, action: str) -> None:
        """Log change to ActivityLog."""
        try:
            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_CRUD,
                operation=action,
                model_name=self.__class__.__name__,
                object_id=str(self.pk) if self.pk else None,
                details={
                    "name": self.name,
                    "code": self.code,
                    "is_active": self.is_active,
                },
            )
        except Exception as e:
            logger.exception(f"Failed to log {action} activity: {e}")

    def save(self, *args, **kwargs):
        """Persist manufacturer data and delegate side-effects to service layer."""
        created = self.pk is None
        old_active = False
        if not created:
            try:
                old_active = Manufacturer.objects.get(pk=self.pk).is_active
            except Manufacturer.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # Delegate audit + discovery side-effects to ManufacturerService
        from micboard.services.manufacturer.manufacturer import ManufacturerService

        ManufacturerService.handle_manufacturer_save(
            manufacturer=self, created=created, old_active=old_active
        )

    def delete(self, *args, **kwargs):
        """Persist deletion and delegate side-effects to service layer."""
        super().delete(*args, **kwargs)
        from micboard.services.manufacturer.manufacturer import ManufacturerService

        ManufacturerService.handle_manufacturer_delete(manufacturer=self)

    def get_plugin_class(self):
        """Get the plugin class for this manufacturer."""
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        return PluginRegistry.get_plugin_class(self.code)
