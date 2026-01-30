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
        """Trigger discovery sync when a manufacturer is activated and log changes."""
        created = self.pk is None
        old_active = False
        if not created:
            try:
                old_active = Manufacturer.objects.get(pk=self.pk).is_active
            except Manufacturer.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # Audit log
        if created:
            self._log_change(action="created")
        else:
            self._log_change(action="modified")

        # Only trigger when not created and when is_active toggled True
        if (not created) and self.is_active and not old_active:
            from micboard.utils.dependencies import HAS_DJANGO_Q

            if HAS_DJANGO_Q:
                try:
                    from django_q.tasks import async_task

                    from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

                    async_task(
                        run_manufacturer_discovery_task,
                        self.pk,
                        False,  # scan_cidrs
                        False,  # scan_fqdns
                    )
                except Exception:
                    logger.exception("Failed to trigger discovery on activation")
            else:
                logger.debug("Django-Q not installed; skipping discovery task trigger")

    def delete(self, *args, **kwargs):
        """Log deletion and delete the manufacturer."""
        self._log_change(action="deleted")
        super().delete(*args, **kwargs)

    def get_plugin_class(self):
        """Get the plugin class for this manufacturer."""
        from micboard.services.plugin_registry import PluginRegistry

        return PluginRegistry.get_plugin_class(self.code)
