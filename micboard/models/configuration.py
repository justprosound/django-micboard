"""
Configuration models for managing manufacturer service configurations.

Allows admin to:
- Enable/disable services
- Override configuration values
- Validate configuration
- Track configuration changes
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar, Dict, Optional

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class ManufacturerConfiguration(models.Model):
    """
    Configuration for a manufacturer service.

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
        User,
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

    def validate(self) -> Dict[str, Any]:
        """
        Validate the configuration.

        Returns:
            Dict with keys:
            - is_valid: boolean
            - errors: list of error messages
        """
        from micboard.services.manufacturer_service import get_service

        errors = []

        # Try to get and initialize the service
        try:
            service = get_service(self.code)
            if not service:
                errors.append(f"Service not found or not enabled: {self.code}")
            else:
                # Attempt health check
                health = service.check_health()
                if health.get("status") == "unhealthy":
                    errors.append(f"Service health check failed: {health.get('message')}")

        except Exception as e:
            errors.append(f"Service initialization failed: {str(e)}")

        # Validate required config fields
        required_fields = self._get_required_fields()
        for field in required_fields:
            if field not in self.config:
                errors.append(f"Missing required configuration: {field}")

        self.validation_errors = {"errors": errors} if errors else {}
        self.is_valid = len(errors) == 0
        self.last_validated = timezone.now()

        if errors:
            logger.warning(
                f"Configuration validation failed for {self.code}",
                extra={"code": self.code, "errors": errors},
            )
        else:
            logger.info(
                f"Configuration validated successfully for {self.code}",
                extra={"code": self.code},
            )

        return {
            "is_valid": self.is_valid,
            "errors": errors,
        }

    def _get_required_fields(self) -> list[str]:
        """Get required configuration fields for this manufacturer."""
        # Map of manufacturer codes to required fields
        required_fields_map: Dict[str, list[str]] = {
            "shure": ["SHURE_API_BASE_URL", "SHURE_API_SHARED_KEY"],
            "sennheiser": ["SENNHEISER_API_BASE_URL"],
        }
        return required_fields_map.get(self.code, [])

    def apply_to_service(self) -> bool:
        """
        Apply this configuration to the running service.

        Returns:
            True if successfully applied, False otherwise
        """
        from micboard.services.manufacturer_service import get_service_registry

        try:
            registry = get_service_registry()
            registry.reload_config(self.code, self.config)
            logger.info(
                f"Configuration applied to service: {self.code}",
                extra={"code": self.code},
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to apply configuration to service {self.code}: {e}",
                exc_info=True,
                extra={"code": self.code},
            )
            return False

    def clean(self) -> None:
        """Validate before saving."""
        if not self.code or not self.name:
            raise ValidationError("Code and name are required")

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and log configuration change."""
        self.full_clean()
        super().save(*args, **kwargs)

        logger.info(
            f"Manufacturer configuration saved: {self.code}",
            extra={
                "code": self.code,
                "is_active": self.is_active,
                "config_keys": list(self.config.keys()),
            },
        )


class ConfigurationAuditLog(models.Model):
    """Audit log for configuration changes."""

    ACTION_CHOICES: ClassVar[tuple] = (
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("validate", "Validate"),
        ("apply", "Apply"),
        ("test", "Test"),
    )

    # What changed
    configuration = models.ForeignKey(
        ManufacturerConfiguration,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        help_text="Configuration that was changed",
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text="Action performed",
    )

    # Who and when
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who performed the action",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Details
    old_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Previous configuration values",
    )
    new_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="New configuration values",
    )
    result = models.CharField(
        max_length=20,
        choices=[("success", "Success"), ("failed", "Failed")],
        default="success",
        help_text="Result of the action",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if action failed",
    )

    class Meta:
        verbose_name = "Configuration Audit Log"
        verbose_name_plural = "Configuration Audit Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["configuration", "-created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.configuration.code} by {self.created_by} at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
