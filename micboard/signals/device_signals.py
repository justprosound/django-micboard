"""Device-related signal handlers for the micboard app.

SIMPLIFIED: Core business logic moved to services.
- wireless_chassis_saved: Logs and broadcasts; sync_discovery delegated to DeviceSyncService
- wireless_unit/rf_channel/assignment changes: Logging only; logic in services

See: micboard.services.device_sync_service.DeviceSyncService
"""

from __future__ import annotations

from typing import Any

# Use exported helpers from micboard.signals (so tests can patch them)
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

try:
    from django_q.tasks import async_task
except ImportError:
    # django-q not installed, provide a no-op function
    def async_task(func, *args, **kwargs):
        # Just call the function synchronously
        func(*args, **kwargs)


import micboard.signals as signals
from micboard.models import (
    DeviceAssignment,
    RFChannel,
    WirelessChassis,
    WirelessUnit,
)
from micboard.tasks.discovery_tasks import sync_receiver_discovery


@receiver(post_save, sender=WirelessChassis)
def wireless_chassis_sync_discovery(
    sender: type[WirelessChassis], instance: WirelessChassis, created: bool, **kwargs: Any
) -> None:
    """Ensure the wireless chassis is known to the manufacturer's discovery list using Django-Q."""
    _ = sender
    # Avoid scheduling background tasks during tests to keep unit tests
    # deterministic. Tests set TESTING=True in settings.
    from django.conf import settings

    if not getattr(settings, "TESTING", False) and instance.ip_address:
        try:
            async_task(sync_receiver_discovery, instance.pk)
        except Exception:
            # During environments without a configured broker don't let
            # scheduling failures break the save operation. Log and continue.
            signals.logger.exception("Failed to schedule sync_receiver_discovery task")


@receiver(post_save, sender=WirelessChassis)
def wireless_chassis_ensure_channels(
    sender: type[WirelessChassis], instance: WirelessChassis, created: bool, **kwargs: Any
) -> None:
    """Auto-create/delete RF channels when chassis model is saved.

    Ensures channel count matches the device model's capacity.
    """
    _ = sender  # Mark as intentionally unused
    try:
        # When chassis is newly created, ensure channels are created based on model
        # Also run on updates in case model changed
        created_count, deleted_count = instance.ensure_channel_count()

        if created_count > 0:
            signals.logger.info(
                "Auto-created %d RF channels for %s (%s)",
                created_count,
                instance.device_name,
                instance.device_type,
            )
        if deleted_count > 0:
            signals.logger.info(
                "Auto-deleted %d excess RF channels for %s",
                deleted_count,
                instance.device_name,
            )
    except Exception:
        signals.logger.exception(
            "Error ensuring channel count for chassis: %s", instance.device_name
        )


@receiver(post_save, sender=WirelessChassis)
def wireless_chassis_saved(
    sender: type[WirelessChassis], instance: WirelessChassis, created: bool, **kwargs: Any
) -> None:
    """Handle chassis save events and broadcast updates via signals only.

    Core business logic is now in DeviceSyncService; this handler is for
    logging and WebSocket notifications.
    """
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.info(
                "Wireless chassis created: %s (%s) at %s",
                instance.device_name,
                instance.device_type,
                instance.ip_address,
            )
            # Clear discovery cache when new chassis is added
            signals.cache.delete("micboard_device_data")
        else:
            # If chassis went offline, notify via WebSocket
            if not instance.is_active:
                try:
                    channel_layer = signals.get_channel_layer()
                    if channel_layer:
                        # group_send expects (group_name, message_dict)
                        signals.async_to_sync(channel_layer.group_send)(
                            "micboard_updates",
                            {
                                "type": "chassis_status",
                                "chassis_id": instance.api_device_id,
                                "is_online": False,
                            },
                        )
                except Exception:
                    signals.logger.exception("Failed to broadcast chassis offline status")
                    # Re-raise so the outer exception handler logs a consistent message
                    raise

            # Log updated after potential background discovery scheduling
            signals.logger.debug("Wireless chassis updated: %s", instance.device_name)
    except Exception:
        signals.logger.exception("Error in wireless_chassis_saved signal handler")


@receiver(pre_delete, sender=WirelessChassis)
def wireless_chassis_pre_delete(
    sender: type[WirelessChassis], instance: WirelessChassis, **kwargs: Any
) -> None:
    """Clean up before chassis deletion."""
    _ = sender  # Mark as intentionally unused
    try:
        # Clear cache entries for this chassis
        cache_keys = [
            f"chassis_{instance.api_device_id}",
            f"channels_{instance.api_device_id}",
            "micboard_device_data",
        ]
        signals.cache.delete_many(cache_keys)
        signals.logger.info("Cleaned up cache for chassis: %s", instance.device_name)
    except Exception:
        signals.logger.exception("Error cleaning up chassis cache")


@receiver(post_delete, sender=WirelessChassis)
def wireless_chassis_deleted(
    sender: type[WirelessChassis], instance: WirelessChassis, **kwargs: Any
) -> None:
    """Handle chassis deletion - broadcast only."""
    _ = sender  # Mark as intentionally unused
    try:
        signals.logger.info(
            "Wireless chassis deleted: %s (%s)", instance.device_name, instance.api_device_id
        )

        # Notify via WebSocket
        try:
            channel_layer = signals.get_channel_layer()
            if channel_layer:
                signals.async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "chassis_deleted", "chassis_id": instance.api_device_id},
                )
        except Exception:
            signals.logger.exception("Failed to broadcast chassis deletion")
            raise
    except Exception:
        signals.logger.exception("Error in wireless_chassis_deleted signal handler")


@receiver(post_save, sender=RFChannel)
def rf_channel_saved(
    sender: type[RFChannel], instance: RFChannel, created: bool, **kwargs: Any
) -> None:
    """Handle RF channel save events - logging only."""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.debug(
                "RF channel created: %s channel %d",
                instance.chassis.device_name,
                instance.channel_number,
            )
    except Exception:
        signals.logger.exception("Error in rf_channel_saved signal handler")


@receiver(post_save, sender=WirelessUnit)
def wireless_unit_saved(
    sender: type[WirelessUnit], instance: WirelessUnit, created: bool, **kwargs: Any
) -> None:
    """Handle wireless unit save events - logging only."""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.debug(
                "Wireless unit created: %s (%s)", instance.device_name, instance.device_type
            )
    except Exception:
        signals.logger.exception("Error in wireless_unit_saved signal handler")


@receiver(post_save, sender=DeviceAssignment)
def assignment_saved(
    sender: type[DeviceAssignment], instance: DeviceAssignment, created: bool, **kwargs: Any
) -> None:
    """Handle device assignment changes - logging only.

    Business logic for assignment creation/updates is in AssignmentService.
    This handler only logs for audit purposes.
    """
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.info(
                "Assignment created: %s -> RF channel (priority: %s)",
                instance.user.username,
                instance.priority,
            )
        else:
            signals.logger.debug("Assignment updated: %s", instance.user.username)
    except Exception:
        signals.logger.exception("Error in assignment_saved signal handler")
