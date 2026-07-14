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
                summary=f"{action} {self.__class__.__name__}: {self.name}",
                object_id=str(self.pk) if self.pk else None,
                details={
                    "name": self.name,
                    "code": self.code,
                    "is_active": self.is_active,
                    "model_name": self.__class__.__name__,
                },
            )
        except Exception as e:
            logger.exception("Failed to log %s activity: %s", action, e)

    def save(self, *args, **kwargs):
        """Persist manufacturer data and delegate side effects to the service layer."""
        from micboard.services.manufacturer.signals import (
            save_manufacturer as _save,
        )

        _save(self, *args, **kwargs)

    def delete(self, *args, **kwargs):
        """Persist deletion and delegate side effects to the service layer."""
        from micboard.services.manufacturer.signals import (
            delete_manufacturer as _delete,
        )

        return _delete(self, *args, **kwargs)

    def get_plugin_class(self):
        """Get the plugin class for this manufacturer."""
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        return PluginRegistry.get_plugin_class(self.code)
