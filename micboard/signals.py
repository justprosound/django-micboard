"""
Signals for the micboard app.
"""

import logging
import os
import sys
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import Signal, receiver

from .models import (
    Channel,
    DeviceAssignment,
    DiscoveryCIDR,
    DiscoveryFQDN,
    Manufacturer,
    MicboardConfig,
    Receiver,
    Transmitter,
)

logger = logging.getLogger(__name__)

# Signal emitted when devices are polled/updated from a manufacturer API.
# Payload should include 'manufacturer' (Manufacturer instance or code)
# and 'data' (serialized structure for broadcasting).
devices_polled = Signal()


def _is_test_mode() -> bool:
    """Return True when running under test/pytest environment.

    Centralized helper so multiple signal handlers can check test mode
    without redefining the same logic.
    """
    if getattr(settings, "TESTING", False):
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    if "pytest" in sys.modules:
        return True
    return False


@receiver(post_save, sender=Receiver)
def receiver_sync_discovery(
    sender: type[Receiver], instance: Receiver, created: bool, **kwargs: Any
) -> None:
    """Ensure the receiver is known to the manufacturer's discovery list.

    This runs in a background thread to avoid blocking request/management flows.
    """
    _ = sender

    def _sync():
        try:
            # Delegate to the central discovery sync helper so all logic lives in one place
            from micboard.manufacturers.shure.discovery_sync import run_discovery_sync

            run_discovery_sync(instance.manufacturer.code, scan_cidrs=False, scan_fqdns=False)
        except Exception:
            logger.exception("Error in receiver discovery sync background task")

    def _start_thread():
        try:
            import threading

            t = threading.Thread(target=_sync, daemon=True)
            t.start()
        except Exception:
            logger.exception("Failed to start background thread for discovery sync")

    # In test environments, avoid starting background threads to prevent DB connection/race issues
    if _is_test_mode():
        # Do not start background thread during tests
        logger.debug("Skipping background discovery sync in test mode for receiver %s", instance)
    else:
        # Ensure the thread starts after DB transaction commits
        try:
            transaction.on_commit(_start_thread)
        except Exception:
            # Fall back to starting immediately if on_commit not available
            _start_thread()


@receiver(post_save, sender=Receiver)
def receiver_saved(
    sender: type[Receiver], instance: Receiver, created: bool, **kwargs: Any
) -> None:
    """Handle receiver save events and broadcast updates"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            logger.info(
                "Receiver created: %s (%s) at %s",
                instance.name,
                instance.device_type,
                instance.ip,
            )
            # Clear discovery cache when new receiver is added
            cache.delete("micboard_device_data")
        else:
            # If receiver went offline, notify via WebSocket
            if not instance.is_active:
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            channel_layer.group_send(
                                "micboard_updates",
                                {
                                    "type": "receiver_status",
                                    "receiver_id": instance.api_device_id,
                                    "is_active": False,
                                },
                            )
                        )
                except Exception:
                    logger.exception("Failed to broadcast receiver offline status")
                    # Re-raise so the outer exception handler logs a consistent message
                    raise

            # Log updated after potential background discovery scheduling
            logger.debug("Receiver updated: %s", instance.name)
    except Exception:
        logger.exception("Error in receiver_saved signal handler")


@receiver(pre_delete, sender=Receiver)
def receiver_pre_delete(sender: type[Receiver], instance: Receiver, **kwargs: Any) -> None:
    """Clean up before receiver deletion"""
    _ = sender  # Mark as intentionally unused
    try:
        # Clear cache entries for this receiver
        cache_keys = [
            f"receiver_{instance.api_device_id}",
            f"channels_{instance.api_device_id}",
            "micboard_device_data",
        ]
        cache.delete_many(cache_keys)
        logger.info("Cleaned up cache for receiver: %s", instance.name)
    except Exception:
        logger.exception("Error cleaning up receiver cache")


@receiver(post_delete, sender=Receiver)
def receiver_deleted(sender: type[Receiver], instance: Receiver, **kwargs: Any) -> None:
    """Handle receiver deletion"""
    _ = sender  # Mark as intentionally unused
    try:
        logger.info("Receiver deleted: %s (%s)", instance.name, instance.api_device_id)

        # Notify via WebSocket
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    channel_layer.group_send(
                        "micboard_updates",
                        {
                            "type": "receiver_deleted",
                            "receiver_id": instance.api_device_id,
                        },
                    )
                )
        except Exception:
            logger.exception("Failed to broadcast receiver deletion")
            raise
    except Exception:
        logger.exception("Error in receiver_deleted signal handler")


@receiver(post_save, sender=Channel)
def channel_saved(sender: type[Channel], instance: Channel, created: bool, **kwargs: Any) -> None:
    """Handle channel save events"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            logger.debug(
                "Channel created: %s channel %d",
                instance.receiver.name,
                instance.channel_number,
            )
    except Exception:
        logger.exception("Error in channel_saved signal handler")


@receiver(post_save, sender=Transmitter)
def transmitter_saved(
    sender: type[Transmitter], instance: Transmitter, created: bool, **kwargs: Any
) -> None:
    """Handle transmitter save events"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            logger.debug("Transmitter created for slot %d", instance.slot)
    except Exception:
        logger.exception("Error in transmitter_saved signal handler")


@receiver(post_save, sender=DeviceAssignment)
def assignment_saved(
    sender: type[DeviceAssignment], instance: DeviceAssignment, created: bool, **kwargs: Any
) -> None:
    """Handle device assignment changes"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            logger.info(
                "Assignment created: %s -> %s (priority: %s)",
                instance.user.username,
                instance.channel,
                instance.priority,
            )
        else:
            logger.debug("Assignment updated: %s -> %s", instance.user.username, instance.channel)
    except Exception:
        logger.exception("Error in assignment_saved signal handler")


@receiver(post_save, sender=MicboardConfig)
def micboardconfig_saved(
    sender: type[MicboardConfig], instance: MicboardConfig, created: bool, **kwargs: Any
) -> None:
    """Trigger discovery scans when SHURE discovery config changes for a manufacturer."""
    _ = sender
    try:
        if instance.key not in ("SHURE_DISCOVERY_CIDRS", "SHURE_DISCOVERY_FQDNS"):
            return

        # Run scan for the associated manufacturer in a background thread
        def _scan():
            try:
                from micboard.manufacturers.shure.discovery_sync import run_discovery_sync

                result = run_discovery_sync(
                    instance.manufacturer.code, scan_cidrs=True, scan_fqdns=True
                )
                logger.info("Discovery scan result: %s", result)
            except Exception:
                logger.exception("Error running discovery scan from MicboardConfig signal")

        def _start_scan():
            try:
                import threading

                t = threading.Thread(target=_scan, daemon=True)
                t.start()
            except Exception:
                logger.exception("Failed to start thread for MicboardConfig discovery scan")

        # Avoid starting background discovery during tests
        if _is_test_mode():
            logger.debug(
                "Skipping MicboardConfig discovery scan in test mode for %s", instance.manufacturer
            )
        else:
            try:
                transaction.on_commit(_start_scan)
            except Exception:
                _start_scan()
    except Exception:
        logger.exception("Error in micboardconfig_saved signal handler")


@receiver(post_save, sender=DiscoveryCIDR)
@receiver(post_delete, sender=DiscoveryCIDR)
def discovery_cidr_changed(
    sender: type[DiscoveryCIDR], instance: DiscoveryCIDR, **kwargs: Any
) -> None:
    """Trigger a scan when CIDR entries change for a manufacturer."""
    try:

        def _run():
            try:
                from micboard.manufacturers.shure.discovery_sync import run_discovery_sync

                run_discovery_sync(instance.manufacturer.code, scan_cidrs=True)
            except Exception:
                logger.exception("Error running discovery sync for CIDR change: %s", instance)

        def _start_run():
            try:
                import threading

                t = threading.Thread(target=_run, daemon=True)
                t.start()
            except Exception:
                logger.exception("Failed to start thread for CIDR change scan")

        if _is_test_mode():
            logger.debug("Skipping CIDR discovery scan in test mode for %s", instance)
        else:
            try:
                transaction.on_commit(_start_run)
            except Exception:
                _start_run()
    except Exception:
        logger.exception("Failed to start thread for CIDR change scan")


@receiver(post_save, sender=DiscoveryFQDN)
@receiver(post_delete, sender=DiscoveryFQDN)
def discovery_fqdn_changed(
    sender: type[DiscoveryFQDN], instance: DiscoveryFQDN, **kwargs: Any
) -> None:
    """Trigger a scan when FQDN entries change for a manufacturer."""
    try:

        def _run():
            try:
                from micboard.manufacturers.shure.discovery_sync import run_discovery_sync

                run_discovery_sync(instance.manufacturer.code, scan_fqdns=True)
            except Exception:
                logger.exception("Error running discovery sync for FQDN change: %s", instance)

        def _start_run():
            try:
                import threading

                t = threading.Thread(target=_run, daemon=True)
                t.start()
            except Exception:
                logger.exception("Failed to start thread for FQDN change scan")

        if _is_test_mode():
            logger.debug("Skipping FQDN discovery scan in test mode for %s", instance)
        else:
            try:
                transaction.on_commit(_start_run)
            except Exception:
                _start_run()
    except Exception:
        logger.exception("Failed to start thread for FQDN change scan")


@receiver(post_save, sender=Manufacturer)
def manufacturer_saved(
    sender: type[Manufacturer], instance: Manufacturer, created: bool, **kwargs: Any
) -> None:
    """Trigger discovery sync when a manufacturer is added or activated."""
    _ = sender
    try:
        # Only trigger when not created and when is_active toggled True
        if (not created) and instance.is_active:

            def _run():
                try:
                    from micboard.manufacturers.shure.discovery_sync import run_discovery_sync

                    result = run_discovery_sync(instance.code, scan_cidrs=False, scan_fqdns=False)
                    logger.info("Discovery sync for manufacturer %s: %s", instance.code, result)
                except Exception:
                    logger.exception(
                        "Error running discovery sync for manufacturer %s", instance.code
                    )

            def _start_run():
                try:
                    import threading

                    t = threading.Thread(target=_run, daemon=True)
                    t.start()
                except Exception:
                    logger.exception("Failed to start thread for manufacturer discovery sync")

            if _is_test_mode():
                logger.debug(
                    "Skipping manufacturer discovery sync in test mode for %s", instance.code
                )
            else:
                try:
                    transaction.on_commit(_start_run)
                except Exception:
                    _start_run()
    except Exception:
        logger.exception("Error in manufacturer_saved signal handler")


@receiver(devices_polled)
def handle_devices_polled(sender, *, manufacturer=None, data=None, **kwargs):
    """Broadcast polled device data to WebSocket clients.

    The signal centralizes broadcasting logic so callers (management commands,
    discovery sync) don't need to interact with Channels directly.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.debug("No channel layer configured; skipping broadcast")
            return

        async_to_sync(channel_layer.group_send)(
            "micboard_updates", {"type": "device_update", "data": data}
        )
        logger.debug(
            "Broadcasted device update for manufacturer %s",
            getattr(manufacturer, "code", str(manufacturer)),
        )
    except Exception:
        logger.exception("Failed to broadcast devices_polled signal payload")
