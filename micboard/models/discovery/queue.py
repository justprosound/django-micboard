"""Discovery queue and device movement tracking."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class DiscoveryQueue(models.Model):
    """Staging area for discovered devices awaiting admin approval before import.

    Implements the "Do you want to import these discovered items?" workflow.
    """

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("imported", "Imported"),
        ("duplicate", "Duplicate (Skipped)"),
    ]

    # Device identification
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="Manufacturer of the discovered device",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Device serial number (primary deduplication key)",
    )
    api_device_id = models.CharField(
        max_length=100,
        help_text="API device identifier",
    )
    ip = models.GenericIPAddressField(
        protocol="both",
        help_text="Current IP address of discovered device",
    )

    # Device metadata
    device_type = models.CharField(
        max_length=20,
        help_text="Device role (receiver/transmitter/transceiver)",
    )
    model = models.CharField(
        max_length=50,
        blank=True,
        help_text="Full model number (e.g., ULXD4D)",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Device name from API",
    )
    firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Firmware version",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Additional device metadata from discovery",
    )

    # Workflow state
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="Approval workflow status",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this device was discovered",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this device was reviewed by admin",
    )
    reviewed_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Admin who reviewed this device",
    )
    notes = models.TextField(
        blank=True,
        help_text="Admin notes about this discovery",
    )

    # Deduplication tracking
    existing_device = models.ForeignKey(
        "micboard.WirelessChassis",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discovery_queue_entries",
        help_text="Existing device if this is a duplicate/movement",
    )
    is_duplicate = models.BooleanField(
        default=False,
        help_text="True if serial_number matches existing device",
    )
    is_ip_conflict = models.BooleanField(
        default=False,
        help_text="True if IP is already in use by different device",
    )
    is_duplicate_api_id = models.BooleanField(
        default=False,
        help_text="True if API device ID duplicated within same manufacturer",
    )
    api_id_conflict_count = models.IntegerField(
        default=0,
        help_text="Number of other devices with same API device ID",
    )

    class Meta:
        verbose_name = "Discovery Queue Entry"
        verbose_name_plural = "Discovery Queue"
        ordering: ClassVar[list[str]] = ["-discovered_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "discovered_at"]),
            models.Index(fields=["manufacturer", "serial_number"]),
            models.Index(fields=["ip"]),
        ]

    def __str__(self) -> str:
        status_display = self.get_status_display()
        if self.serial_number:
            return f"{self.name} (S/N: {self.serial_number}) - {status_display}"
        return f"{self.name} @ {self.ip} - {status_display}"

    def check_for_duplicates(self) -> dict[str, Any]:
        """Check if this device already exists in the system."""
        from micboard.models.hardware import WirelessChassis

        result: dict[str, Any] = {
            "is_duplicate": False,
            "is_ip_conflict": False,
            "existing_device": None,
            "conflict_type": None,
        }

        # Check for serial number match (primary deduplication)
        if self.serial_number:
            try:
                existing = WirelessChassis.objects.get(serial_number=self.serial_number)
                result["is_duplicate"] = True
                result["existing_device"] = existing

                # Check if IP changed (device moved)
                if existing.ip != self.ip:
                    result["conflict_type"] = "moved"
                elif existing.manufacturer != self.manufacturer:
                    result["conflict_type"] = "manufacturer_mismatch"
                else:
                    result["conflict_type"] = "duplicate"

                return result
            except WirelessChassis.DoesNotExist:
                pass

        # Check for IP conflict (different device, same IP)
        try:
            existing = WirelessChassis.objects.get(ip=self.ip)
            result["is_ip_conflict"] = True
            result["existing_device"] = existing

            # If serial numbers don't match, it's a true conflict
            if self.serial_number and existing.serial_number != self.serial_number:
                result["conflict_type"] = "ip_conflict"
            else:
                result["conflict_type"] = "metadata_update"

        except WirelessChassis.DoesNotExist:
            pass

        return result


class DeviceMovementLog(models.Model):
    """Tracks when devices change IP addresses or physical locations.

    Used for auditing and alerting when devices move in the network.
    """

    device = models.ForeignKey(
        "micboard.WirelessChassis",
        on_delete=models.CASCADE,
        related_name="movement_logs",
        help_text="Device that moved",
    )

    # IP address changes
    old_ip = models.GenericIPAddressField(
        protocol="both",
        null=True,
        blank=True,
        help_text="Previous IP address",
    )
    new_ip = models.GenericIPAddressField(
        protocol="both",
        null=True,
        blank=True,
        help_text="New IP address",
    )

    # Location changes
    old_location = models.ForeignKey(
        "micboard.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movement_logs_from",
        help_text="Previous location",
    )
    new_location = models.ForeignKey(
        "micboard.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movement_logs_to",
        help_text="New location",
    )

    # Movement metadata
    detected_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the movement was detected",
    )
    detected_by = models.CharField(
        max_length=100,
        default="auto",
        help_text="How movement was detected (auto/manual/sync)",
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for movement or additional notes",
    )
    acknowledged = models.BooleanField(
        default=False,
        help_text="Whether admin has acknowledged this movement",
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When movement was acknowledged",
    )
    acknowledged_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Admin who acknowledged the movement",
    )

    class Meta:
        verbose_name = "Device Movement Log"
        verbose_name_plural = "Device Movement Logs"
        ordering: ClassVar[list[str]] = ["-detected_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["device", "detected_at"]),
            models.Index(fields=["acknowledged", "detected_at"]),
        ]

    def __str__(self) -> str:
        parts = []
        if self.old_ip and self.new_ip and self.old_ip != self.new_ip:
            parts.append(f"IP: {self.old_ip} → {self.new_ip}")
        if self.old_location and self.new_location and self.old_location != self.new_location:
            parts.append(f"Location: {self.old_location.name} → {self.new_location.name}")

        change_desc = ", ".join(parts) if parts else "No changes"
        return f"{self.device.name} - {change_desc} @ {self.detected_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def movement_type(self) -> str:
        """Get human-readable movement type."""
        if self.old_ip and self.new_ip and self.old_ip != self.new_ip:
            if self.old_location and self.new_location and self.old_location != self.new_location:
                return "ip_and_location"
            return "ip_only"
        if self.old_location and self.new_location and self.old_location != self.new_location:
            return "location_only"
        return "unknown"
