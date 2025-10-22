"""
Device-related signal handlers for the micboard app.
"""

from __future__ import annotations

from typing import Any

# Use exported helpers from micboard.signals (so tests can patch them)
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver
from django_q.tasks import async_task

import micboard.signals as signals
from micboard.models import (
    Channel,
    DeviceAssignment,
    Receiver,
    Transmitter,
)
from micboard.tasks.discovery_tasks import sync_receiver_discovery


@receiver(post_save, sender=Receiver)
def receiver_sync_discovery(
    sender: type[Receiver], instance: Receiver, created: bool, **kwargs: Any
) -> None:
    """
    Ensure the receiver is known to the manufacturer's discovery list using Django-Q.
    """
    _ = sender
    # Avoid scheduling background tasks during tests to keep unit tests
    # deterministic. Tests set TESTING=True in settings.
    from django.conf import settings

    if not getattr(settings, "TESTING", False) and instance.ip:
        try:
            async_task(sync_receiver_discovery, instance.pk)
        except Exception:
            # During environments without a configured broker don't let
            # scheduling failures break the save operation. Log and continue.
            signals.logger.exception("Failed to schedule sync_receiver_discovery task")


@receiver(post_save, sender=Receiver)
def receiver_saved(
    sender: type[Receiver], instance: Receiver, created: bool, **kwargs: Any
) -> None:
    """Handle receiver save events and broadcast updates"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.info(
                "Receiver created: %s (%s) at %s",
                instance.name,
                instance.device_type,
                instance.ip,
            )
            # Clear discovery cache when new receiver is added
            signals.cache.delete("micboard_device_data")
        else:
            # If receiver went offline, notify via WebSocket
            if not instance.is_active:
                try:
                    channel_layer = signals.get_channel_layer()
                    if channel_layer:
                        # group_send expects (group_name, message_dict)
                        signals.async_to_sync(channel_layer.group_send)(
                            "micboard_updates",
                            {
                                "type": "receiver_status",
                                "receiver_id": instance.api_device_id,
                                "is_active": False,
                            },
                        )
                except Exception:
                    signals.logger.exception("Failed to broadcast receiver offline status")
                    # Re-raise so the outer exception handler logs a consistent message
                    raise

            # Log updated after potential background discovery scheduling
            signals.logger.debug("Receiver updated: %s", instance.name)
    except Exception:
        signals.logger.exception("Error in receiver_saved signal handler")


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
        signals.cache.delete_many(cache_keys)
        signals.logger.info("Cleaned up cache for receiver: %s", instance.name)
    except Exception:
        signals.logger.exception("Error cleaning up receiver cache")


@receiver(post_delete, sender=Receiver)
def receiver_deleted(sender: type[Receiver], instance: Receiver, **kwargs: Any) -> None:
    """Handle receiver deletion"""
    _ = sender  # Mark as intentionally unused
    try:
        signals.logger.info("Receiver deleted: %s (%s)", instance.name, instance.api_device_id)

        # Notify via WebSocket
        try:
            channel_layer = signals.get_channel_layer()
            if channel_layer:
                signals.async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "receiver_deleted", "receiver_id": instance.api_device_id},
                )
        except Exception:
            signals.logger.exception("Failed to broadcast receiver deletion")
            raise
    except Exception:
        signals.logger.exception("Error in receiver_deleted signal handler")


@receiver(post_save, sender=Channel)
def channel_saved(sender: type[Channel], instance: Channel, created: bool, **kwargs: Any) -> None:
    """Handle channel save events"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.debug(
                "Channel created: %s channel %d",
                instance.receiver.name,
                instance.channel_number,
            )
    except Exception:
        signals.logger.exception("Error in channel_saved signal handler")


@receiver(post_save, sender=Transmitter)
def transmitter_saved(
    sender: type[Transmitter], instance: Transmitter, created: bool, **kwargs: Any
) -> None:
    """Handle transmitter save events"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.debug("Transmitter created for slot %d", instance.slot)
    except Exception:
        signals.logger.exception("Error in transmitter_saved signal handler")


@receiver(post_save, sender=DeviceAssignment)
def assignment_saved(
    sender: type[DeviceAssignment], instance: DeviceAssignment, created: bool, **kwargs: Any
) -> None:
    """Handle device assignment changes"""
    _ = sender  # Mark as intentionally unused
    try:
        if created:
            signals.logger.info(
                "Assignment created: %s -> %s (priority: %s)",
                instance.user.username,
                instance.channel,
                instance.priority,
            )
        else:
            signals.logger.debug(
                "Assignment updated: %s -> %s", instance.user.username, instance.channel
            )
    except Exception:
        signals.logger.exception("Error in assignment_saved signal handler")
