"""Manufacturer model for device vendor registry."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class Manufacturer(models.Model):
    """Represents a device manufacturer."""

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

    def save(self, *args, **kwargs):
        """Trigger discovery sync when a manufacturer is activated."""
        created = self.pk is None
        old_active = False
        if not created:
            try:
                old_active = Manufacturer.objects.get(pk=self.pk).is_active
            except Manufacturer.DoesNotExist:
                pass

        super().save(*args, **kwargs)

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
                    # Don't let task scheduling failures break the save
                    import logging

                    logging.getLogger(__name__).exception("Failed to trigger discovery on activation")
            else:
                import logging
                logging.getLogger(__name__).debug("Django-Q not installed; skipping discovery task trigger")

    def get_plugin_class(self):
        """Get the plugin class for this manufacturer."""
        from micboard.manufacturers import get_manufacturer_plugin

        return get_manufacturer_plugin(self.code)
