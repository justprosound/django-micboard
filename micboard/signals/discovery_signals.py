"""
Discovery-related signal handlers for the micboard app.
"""

# Discovery-related signal handlers for the micboard app.
from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_q.tasks import async_task

from micboard.models import (
    DiscoveryCIDR,
    DiscoveryFQDN,
    Manufacturer,
    MicboardConfig,
)
from micboard.tasks.discovery_tasks import run_manufacturer_discovery_task

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MicboardConfig)
def micboardconfig_saved(
    sender: type[MicboardConfig], instance: MicboardConfig, created: bool, **kwargs: Any
) -> None:
    """Trigger discovery scans when SHURE discovery config changes for a manufacturer."""
    _ = sender
    try:
        # This signal handler is specifically for Shure config keys for now.
        # In a multi-vendor setup, this would need to be generalized or each
        # manufacturer would have its own config keys.
        if instance.key not in ("SHURE_DISCOVERY_CIDRS", "SHURE_DISCOVERY_FQDNS"):
            return

        async_task(
            run_manufacturer_discovery_task,
            instance.manufacturer.pk,  # Pass manufacturer ID
            True,  # scan_cidrs
            True,  # scan_fqdns
        )
    except Exception:
        logger.exception("Error in micboardconfig_saved signal handler")


@receiver(post_save, sender=DiscoveryCIDR)
@receiver(post_delete, sender=DiscoveryCIDR)
def discovery_cidr_changed(
    sender: type[DiscoveryCIDR], instance: DiscoveryCIDR, **kwargs: Any
) -> None:
    """Trigger a scan when CIDR entries change for a manufacturer."""
    _ = sender
    try:
        async_task(
            run_manufacturer_discovery_task,
            instance.manufacturer.pk,
            True,  # scan_cidrs
            False,  # scan_fqdns
        )
    except Exception:
        logger.exception("Failed to enqueue CIDR change scan")


@receiver(post_save, sender=DiscoveryFQDN)
@receiver(post_delete, sender=DiscoveryFQDN)
def discovery_fqdn_changed(
    sender: type[DiscoveryFQDN], instance: DiscoveryFQDN, **kwargs: Any
) -> None:
    """Trigger a scan when FQDN entries change for a manufacturer."""
    _ = sender
    try:
        async_task(
            run_manufacturer_discovery_task,
            instance.manufacturer.pk,
            False,  # scan_cidrs
            True,  # scan_fqdns
        )
    except Exception:
        logger.exception("Failed to enqueue FQDN change scan")


@receiver(post_save, sender=Manufacturer)
def manufacturer_saved(
    sender: type[Manufacturer], instance: Manufacturer, created: bool, **kwargs: Any
) -> None:
    """Trigger discovery sync when a manufacturer is added or activated."""
    _ = sender
    try:
        # Only trigger when not created and when is_active toggled True
        if (not created) and instance.is_active:
            async_task(
                run_manufacturer_discovery_task,
                instance.pk,
                False,  # scan_cidrs
                False,  # scan_fqdns
            )
    except Exception:
        logger.exception("Error in manufacturer_saved signal handler")
