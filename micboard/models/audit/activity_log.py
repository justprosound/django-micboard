"""Activity logging models for comprehensive audit trail.

Tracks all CRUD operations, service syncs, and system events.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class ActivityLog(models.Model):
    """Comprehensive activity log for all system operations.

    Tracks CRUD operations, service sync events, and system activities.
    """

    # Activity types
    ACTIVITY_CRUD = "crud"
    ACTIVITY_SERVICE = "service"
    ACTIVITY_SYNC = "sync"
    ACTIVITY_CONFIG = "config"
    ACTIVITY_DISCOVERY = "discovery"
    ACTIVITY_ALERT = "alert"
    ACTIVITY_COMPLIANCE = "compliance"

    ACTIVITY_CHOICES: ClassVar[tuple] = (
        (ACTIVITY_CRUD, "CRUD Operation"),
        (ACTIVITY_SERVICE, "Service Activity"),
        (ACTIVITY_SYNC, "Device Sync"),
        (ACTIVITY_CONFIG, "Configuration"),
        (ACTIVITY_DISCOVERY, "Discovery"),
        (ACTIVITY_ALERT, "Alert"),
        (ACTIVITY_COMPLIANCE, "Compliance Check"),
    )

    # Operation types
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    START = "start"
    STOP = "stop"
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"

    OPERATION_CHOICES: ClassVar[tuple] = (
        (CREATE, "Create"),
        (READ, "Read"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
        (START, "Start"),
        (STOP, "Stop"),
        (SUCCESS, "Success"),
        (FAILURE, "Failure"),
        (WARNING, "Warning"),
    )

    # Activity metadata
    activity_type = models.CharField(
        max_length=20,
        choices=ACTIVITY_CHOICES,
        default=ACTIVITY_CRUD,
        db_index=True,
        help_text="Type of activity",
    )
    operation = models.CharField(
        max_length=20,
        choices=OPERATION_CHOICES,
        default=CREATE,
        db_index=True,
        help_text="Operation performed",
    )

    # Actor
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
        help_text="User who triggered the activity (null for system)",
    )
    service_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Service code (for service activities)",
    )

    # Subject (generic)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
        help_text="Content type of the affected object",
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the affected object",
    )
    content_object = GenericForeignKey("content_type", "object_id")

    # Description
    summary = models.CharField(
        max_length=255,
        help_text="Brief summary of the activity",
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed information as JSON",
    )

    # State changes (for CRUD)
    old_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Previous values (for update operations)",
    )
    new_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="New values (for create/update operations)",
    )

    # Status and errors
    status = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("warning", "Warning"),
        ],
        default="success",
        db_index=True,
        help_text="Result status",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if operation failed",
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When activity occurred",
    )
    updated_at = models.DateTimeField(auto_now=True)

    # Metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the client",
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        help_text="User agent string",
    )

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity_type", "-created_at"]),
            models.Index(fields=["operation", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        if self.content_object:
            return (
                f"{self.get_activity_type_display()} - "
                f"{self.get_operation_display()} - {self.content_object}"
            )
        return (
            f"{self.get_activity_type_display()} - {self.get_operation_display()} - {self.summary}"
        )


class ServiceSyncLog(models.Model):
    """Detailed log of service synchronization events."""

    service = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        related_name="sync_logs",
        help_text="Manufacturer being synced",
    )

    sync_type = models.CharField(
        max_length=50,
        choices=[
            ("full", "Full Sync"),
            ("incremental", "Incremental Sync"),
            ("health_check", "Health Check"),
        ],
        help_text="Type of sync",
    )

    started_at = models.DateTimeField(help_text="When sync started")
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When sync completed",
    )

    device_count = models.IntegerField(
        default=0,
        help_text="Total devices synced",
    )
    online_count = models.IntegerField(
        default=0,
        help_text="Devices that came online",
    )
    offline_count = models.IntegerField(
        default=0,
        help_text="Devices that went offline",
    )
    updated_count = models.IntegerField(
        default=0,
        help_text="Devices with updated data",
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("partial", "Partial Success"),
            ("failed", "Failed"),
        ],
        help_text="Sync result",
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error details if failed",
    )

    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional sync details",
    )

    class Meta:
        verbose_name = "Service Sync Log"
        verbose_name_plural = "Service Sync Logs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["service", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.service.name} - {self.get_sync_type_display()} - "
            f"{self.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def duration_seconds(self) -> int:
        """Get sync duration in seconds."""
        if not self.completed_at:
            return 0
        return int((self.completed_at - self.started_at).total_seconds())
