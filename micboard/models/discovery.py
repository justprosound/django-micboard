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

    def get_plugin_class(self):
        """Get the plugin class for this manufacturer."""
        # Import here to avoid circular imports
        from micboard.manufacturers import get_manufacturer_plugin

        return get_manufacturer_plugin(self.code)

    @property
    def receivers(self):
        """Convenience property to access related Receiver objects via ORM.

        Some tests expect Manufacturer.receivers rather than the default
        reverse relation name. This property mirrors the related manager.
        """
        from micboard.models import Receiver

        return Receiver.objects.filter(manufacturer=self)

    @property
    def discovered_devices(self):
        """Convenience property to access related DiscoveredDevice objects."""
        from micboard.models import DiscoveredDevice

        return DiscoveredDevice.objects.filter(manufacturer=self)


class MicboardConfig(models.Model):
    """Global configuration settings"""

    key = models.CharField(max_length=100, help_text="Configuration key")
    value = models.TextField(help_text="Configuration value")
    manufacturer = models.ForeignKey(
        "Manufacturer",
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


class DiscoveryCIDR(models.Model):
    """CIDR ranges to be used for Shure discovery scans."""

    manufacturer = models.ForeignKey(
        "Manufacturer", on_delete=models.CASCADE, help_text="Manufacturer this CIDR applies to"
    )
    cidr = models.CharField(max_length=50, help_text="CIDR range (e.g., 10.0.0.0/22)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discovery CIDR"
        verbose_name_plural = "Discovery CIDRs"
        ordering: ClassVar[list[str]] = ["manufacturer__name", "cidr"]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.cidr}"


class DiscoveryFQDN(models.Model):
    """FQDN patterns or hostnames to resolve for discovery."""

    manufacturer = models.ForeignKey(
        "Manufacturer", on_delete=models.CASCADE, help_text="Manufacturer this FQDN applies to"
    )
    fqdn = models.CharField(max_length=255, help_text="FQDN or pattern (e.g., host.example.com)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discovery FQDN"
        verbose_name_plural = "Discovery FQDNs"
        ordering: ClassVar[list[str]] = ["manufacturer__name", "fqdn"]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.fqdn}"


class DiscoveryJob(models.Model):
    """Records an on-demand or automatic discovery job run."""

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    manufacturer = models.ForeignKey(
        "Manufacturer", on_delete=models.CASCADE, help_text="Manufacturer this job relates to"
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
    """Represents a device discovered on the network but not yet configured"""

    ip = models.GenericIPAddressField(unique=True, help_text="IP address of the discovered device")
    device_type = models.CharField(max_length=20, help_text="Type of discovered device")
    channels = models.PositiveIntegerField(default=0, help_text="Number of channels on the device")
    manufacturer = models.ForeignKey(
        "Manufacturer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The manufacturer of this discovered device",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True, help_text="When this device was first discovered"
    )

    class Meta:
        verbose_name = "Discovered Device"
        verbose_name_plural = "Discovered Devices"
        ordering: ClassVar[list[str]] = ["-discovered_at"]

    def __str__(self) -> str:
        return f"{self.device_type} at {self.ip} ({self.manufacturer.name})"
