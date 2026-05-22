"""Discovery job and configuration models."""

from __future__ import annotations

import warnings
from typing import ClassVar

from django.db import models

from micboard.models.mixins import DiscoveryTriggerMixin


class MicboardConfig(models.Model, DiscoveryTriggerMixin):
    """Global configuration settings."""

    key = models.CharField(max_length=100, help_text="Configuration key")
    value = models.TextField(help_text="Configuration value")
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Manufacturer this config applies to (null for global configs)",
    )

    class Meta:
        verbose_name = "Micboard Configuration"
        verbose_name_plural = "Micboard Configurations"
        ordering: ClassVar[list[str]] = ["manufacturer__name", "key"]
        unique_together: ClassVar[list[list[str]]] = [["key", "manufacturer"]]

    def __str__(self) -> str:
        manufacturer_name = self.manufacturer.name if self.manufacturer else "Global"
        return f"{manufacturer_name}: {self.key}: {self.value}"

    def save(self, *args, **kwargs):
        """Trigger discovery scans when SHURE discovery config changes.

        Deprecated: Use registry_service.save_micboard_config() instead.
        """
        warnings.warn(
            "MicboardConfig.save() is deprecated, "
            "use registry_service.save_micboard_config() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.discovery.registry_service import (
            save_micboard_config as _save,
        )

        _save(self, *args, **kwargs)


class DiscoveryCIDR(models.Model, DiscoveryTriggerMixin):
    """CIDR ranges to be used for discovery scans."""

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="Manufacturer this CIDR applies to",
    )
    cidr = models.CharField(max_length=50, help_text="CIDR range (e.g., 10.0.0.0/22)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discovery CIDR"
        verbose_name_plural = "Discovery CIDRs"
        ordering: ClassVar[list[str]] = ["manufacturer__name", "cidr"]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.cidr}"

    def save(self, *args, **kwargs):
        """Trigger scan when CIDR changes.

        Deprecated: Use registry_service.save_discovery_cidr() instead.
        """
        warnings.warn(
            "DiscoveryCIDR.save() is deprecated, "
            "use registry_service.save_discovery_cidr() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.discovery.registry_service import (
            save_discovery_cidr as _save,
        )

        _save(self, *args, **kwargs)


class DiscoveryFQDN(models.Model, DiscoveryTriggerMixin):
    """FQDN patterns or hostnames to resolve for discovery."""

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="Manufacturer this FQDN applies to",
    )
    fqdn = models.CharField(max_length=255, help_text="FQDN or pattern (e.g., host.example.com)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discovery FQDN"
        verbose_name_plural = "Discovery FQDNs"
        ordering: ClassVar[list[str]] = ["manufacturer__name", "fqdn"]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.fqdn}"

    def save(self, *args, **kwargs):
        """Trigger scan when FQDN changes.

        Deprecated: Use registry_service.save_discovery_fqdn() instead.
        """
        warnings.warn(
            "DiscoveryFQDN.save() is deprecated, "
            "use registry_service.save_discovery_fqdn() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.discovery.registry_service import (
            save_discovery_fqdn as _save,
        )

        _save(self, *args, **kwargs)

    def delete(self, *args, **kwargs):
        """Trigger scan when FQDN removed.

        Deprecated: Use registry_service.delete_discovery_fqdn() instead.
        """
        warnings.warn(
            "DiscoveryFQDN.delete() is deprecated, "
            "use registry_service.delete_discovery_fqdn() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        from micboard.services.discovery.registry_service import (
            delete_discovery_fqdn as _delete,
        )

        return _delete(self, *args, **kwargs)


class DiscoveryJob(models.Model):
    """Records an on-demand or automatic discovery job run."""

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="Manufacturer this job relates to",
    )
    action = models.CharField(max_length=50, help_text="Action (sync/scan)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    items_scanned = models.IntegerField(null=True, blank=True)
    items_submitted = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Discovery Job"
        verbose_name_plural = "Discovery Jobs"
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.action} @ {self.created_at.isoformat()}"


class DiscoveredDevice(models.Model):
    """Represents a device discovered on the network but not yet configured.

    This model is manufacturer-agnostic and stores device discovery information
    from any manufacturer API (Shure, Sennheiser, Audio-Technica, etc.).
    Manufacturer-specific fields are stored in the metadata JSONField.
    """

    # Generic status categories (applicable to all manufacturers)
    STATUS_READY = "ready"  # Device is online and ready to manage
    STATUS_PENDING = "pending"  # Device discovered but not yet ready
    STATUS_INCOMPATIBLE = "incompatible"  # Firmware/API version mismatch
    STATUS_ERROR = "error"  # Communication error
    STATUS_OFFLINE = "offline"  # Device is offline
    STATUS_UNKNOWN = "unknown"  # Status not determined

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (STATUS_READY, "Ready to Manage"),
        (STATUS_PENDING, "Pending (Not Ready)"),
        (STATUS_INCOMPATIBLE, "Incompatible"),
        (STATUS_ERROR, "Error"),
        (STATUS_OFFLINE, "Offline"),
        (STATUS_UNKNOWN, "Unknown"),
    ]

    # Basic identification (common to all manufacturers)
    ip = models.GenericIPAddressField(
        unique=True,
        help_text="IP address or communication address of the discovered device",
    )
    api_device_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Unique device ID from manufacturer API",
    )
    device_type = models.CharField(
        max_length=50,
        help_text="Type or model of discovered device",
    )
    model = models.CharField(
        max_length=50,
        blank=True,
        help_text="Product model name",
    )
    channels = models.PositiveIntegerField(
        default=0,
        help_text="Number of channels on the device",
    )

    # Manufacturer relationship
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The manufacturer of this discovered device",
    )

    # Generic status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Generic device status (ready, pending, incompatible, error, offline)",
    )

    # Manufacturer-specific data storage
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Manufacturer-specific data. For Shure: compatibility, deviceState, "
            "hardwareIdentity, softwareIdentity, communicationProtocol. "
            "For Sennheiser: device-specific fields from SSCv2 API."
        ),
    )

    # Metadata
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this device was first discovered",
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last time device information was updated",
    )
    notes = models.TextField(
        blank=True,
        help_text="Admin notes about why device cannot be managed or promotion blockers",
    )

    class Meta:
        verbose_name = "Discovered Device"
        verbose_name_plural = "Discovered Devices"
        ordering: ClassVar[list[str]] = ["-discovered_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "manufacturer"]),
            models.Index(fields=["manufacturer", "discovered_at"]),
        ]

    def __str__(self) -> str:
        status = self.get_status_display()
        if self.manufacturer:
            return f"{self.device_type} at {self.ip} [{status}] ({self.manufacturer.name})"
        return f"{self.device_type} at {self.ip} [{status}]"

    def get_status_display_with_icon(self) -> str:
        """Get human-readable status with visual icon.

        Deprecated: move to template layer or admin display methods.
        """
        status_icons = {
            self.STATUS_READY: "✅",
            self.STATUS_PENDING: "🔍",
            self.STATUS_INCOMPATIBLE: "⚠️",
            self.STATUS_ERROR: "❌",
            self.STATUS_OFFLINE: "📴",
            self.STATUS_UNKNOWN: "❓",
        }
        icon = status_icons.get(self.status, "")
        return f"{icon} {self.get_status_display()}"
