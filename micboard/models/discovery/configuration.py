"""Configuration models for managing manufacturer service configurations.

Allows admin to:
- Enable/disable services
- Override configuration values
- Validate configuration
- Track configuration changes
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ManufacturerConfiguration(models.Model):
    """Configuration for a manufacturer service.

    Allows admin-level configuration overrides and validation.
    Replaces environment variables and settings.py configuration.
    """

    # Manufacturer identifiers
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique code for manufacturer (e.g., 'shure', 'sennheiser')",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Shure Incorporated')",
    )

    # Status and control
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this manufacturer service is enabled",
    )

    # Configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Service-specific configuration as JSON",
    )

    # Validation
    validation_errors = models.JSONField(
        default=dict,
        blank=True,
        help_text="Validation errors from last check",
    )
    last_validated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last validation",
    )
    is_valid = models.BooleanField(
        default=False,
        help_text="Whether current configuration is valid",
    )

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manufacturer_config_updates",
        help_text="User who last updated this configuration",
    )

    class Meta:
        verbose_name = "Manufacturer Configuration"
        verbose_name_plural = "Manufacturer Configurations"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.is_active else "✗"
        return f"{status} {self.name} ({self.code})"

    def clean(self) -> None:
        """Validate before saving."""
        if not self.code or not self.name:
            raise ValidationError("Code and name are required")
