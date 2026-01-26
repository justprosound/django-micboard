"""Audit log for configuration changes."""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models

from micboard.models.discovery.configuration import ManufacturerConfiguration


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
        return (
            f"{self.get_action_display()} {self.configuration.code} by {self.created_by} "
            f"at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
