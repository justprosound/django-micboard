"""
Signals for the micboard app.
"""

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models import Channel, DeviceAssignment, Receiver, Transmitter

logger = logging.getLogger(__name__)


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
            logger.debug("Receiver updated: %s", instance.name)

            # If receiver went offline, notify via WebSocket
            if not instance.is_active:
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            "micboard_updates",
                            {
                                "type": "receiver_status",
                                "receiver_id": instance.api_device_id,
                                "is_active": False,
                            },
                        )
                except Exception:
                    logger.exception("Failed to broadcast receiver offline status")
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
                    "micboard_updates",
                    {
                        "type": "receiver_deleted",
                        "receiver_id": instance.api_device_id,
                    },
                )
        except Exception:
            logger.exception("Failed to broadcast receiver deletion")
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
