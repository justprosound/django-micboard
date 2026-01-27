"""Discovery job and configuration models."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class MicboardConfig(models.Model):
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
        """Trigger discovery scans when SHURE discovery config changes."""
        super().save(*args, **kwargs)

        if self.manufacturer and self.key in ("SHURE_DISCOVERY_CIDRS", "SHURE_DISCOVERY_FQDNS"):
            from micboard.utils.dependencies import HAS_DJANGO_Q
            if HAS_DJANGO_Q:
                try:
                    from django_q.tasks import async_task

                    from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

                    async_task(
                        run_manufacturer_discovery_task,
                        self.manufacturer.pk,
                        True,  # scan_cidrs
                        True,  # scan_fqdns
                    )
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception(
                        "Failed to trigger discovery on config change"
                    )
            else:
                import logging
                logging.getLogger(__name__).debug("Django-Q not installed; skipping discovery trigger on config change")


class DiscoveryCIDR(models.Model):
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
        """Trigger scan when CIDR changes."""
        super().save(*args, **kwargs)
        self._trigger_discovery()

    def delete(self, *args, **kwargs):
        """Trigger scan when CIDR removed."""
        manufacturer_pk = self.manufacturer_id
        result = super().delete(*args, **kwargs)
        self._trigger_discovery(manufacturer_pk)
        return result

    def _trigger_discovery(self, manufacturer_pk=None):
        from micboard.utils.dependencies import HAS_DJANGO_Q
        if HAS_DJANGO_Q:
            try:
                from django_q.tasks import async_task

                from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

                async_task(
                    run_manufacturer_discovery_task,
                    manufacturer_pk or self.manufacturer_id,
                    True,  # scan_cidrs
                    False,  # scan_fqdns
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Failed to trigger discovery on CIDR change")
        else:
            import logging
            logging.getLogger(__name__).debug("Django-Q not installed; skipping discovery trigger on CIDR change")


class DiscoveryFQDN(models.Model):
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
        """Trigger scan when FQDN changes."""
        super().save(*args, **kwargs)
        self._trigger_discovery()

    def delete(self, *args, **kwargs):
        """Trigger scan when FQDN removed."""
        manufacturer_pk = self.manufacturer_id
        result = super().delete(*args, **kwargs)
        self._trigger_discovery(manufacturer_pk)
        return result

    def _trigger_discovery(self, manufacturer_pk=None):
        from micboard.utils.dependencies import HAS_DJANGO_Q
        if HAS_DJANGO_Q:
            try:
                from django_q.tasks import async_task

                from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

                async_task(
                    run_manufacturer_discovery_task,
                    manufacturer_pk or self.manufacturer_id,
                    False,  # scan_cidrs
                    True,  # scan_fqdns
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Failed to trigger discovery on FQDN change")
        else:
            import logging
            logging.getLogger(__name__).debug("Django-Q not installed; skipping discovery trigger on FQDN change")


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
    """Represents a device discovered on the network but not yet configured."""

    ip = models.GenericIPAddressField(unique=True, help_text="IP address of the discovered device")
    device_type = models.CharField(max_length=20, help_text="Type of discovered device")
    channels = models.PositiveIntegerField(default=0, help_text="Number of channels on the device")
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
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
