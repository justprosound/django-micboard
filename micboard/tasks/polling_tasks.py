"""
Polling-related background tasks for the micboard app.
"""

# Polling-related background tasks for the micboard app.
from __future__ import annotations

import logging

from django.utils import timezone

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    Channel,
    Manufacturer,
    Receiver,
    Transmitter,
)
from micboard.serializers import ReceiverSummarySerializer
from micboard.signals.broadcast_signals import api_health_changed, devices_polled
from micboard.services.alerts import check_device_offline_alerts, check_transmitter_alerts

logger = logging.getLogger(__name__)


def poll_manufacturer_devices(manufacturer_id: int):
    """
    Task to poll devices for a specific manufacturer and update models.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        # Check API health before polling
        health_data = plugin.get_client().check_health()
        is_healthy = health_data.get("status") == "healthy"
        logger.info("API health for %s: %s", manufacturer.name, health_data)

        # Emit api_health_changed signal
        api_health_changed.send(sender=None, manufacturer=manufacturer, health_data=health_data)

        if not is_healthy:
            logger.warning("Skipping poll for %s due to unhealthy API.", manufacturer.name)
            return

        api_data = plugin.get_devices()
        if api_data:
            updated_count = _update_models_from_api_data(api_data, manufacturer, plugin)
            logger.info("Polled %d devices from %s", updated_count, manufacturer.name)

            # Broadcast updated list via devices_polled signal
            serialized_data = {
                "receivers": ReceiverSummarySerializer(
                    Receiver.objects.filter(manufacturer=manufacturer), many=True
                ).data
            }
            devices_polled.send(sender=None, manufacturer=manufacturer, data=serialized_data)
        else:
            logger.warning("No device data received from %s", manufacturer.name)

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for device polling task.", manufacturer_id
        )
    except Exception as e:
        logger.exception("Error polling devices for manufacturer ID %s: %s", manufacturer_id, e)


def _update_models_from_api_data(api_data, manufacturer, plugin):
    """
    Helper function to update Django models with API data.
    Extracted from poll_devices.py management command.
    """
    updated_count = 0
    active_receiver_ids = []

    for device_data in api_data:
        try:
            # Transform API data to micboard format
            transformed_data = plugin.transform_device_data(device_data)
            if not transformed_data:
                continue

            api_device_id = transformed_data["api_device_id"]

            # Create/update Receiver
            receiver = _update_receiver(transformed_data, manufacturer, api_device_id)
            active_receiver_ids.append(receiver.id)

            # Update channels and transmitters
            channels_data = plugin.get_device_channels(api_device_id)
            for channel_info in channels_data:
                _update_channel_and_transmitter(receiver, channel_info, plugin, api_device_id)

            updated_count += 1

        except Exception:
            logger.exception("Error updating device %s", api_device_id)
            continue

    # Mark receivers that were not in the API data as offline
    _mark_offline_receivers(manufacturer, active_receiver_ids)

    return updated_count


def _update_receiver(transformed_data, manufacturer, api_device_id):
    """Update or create a receiver from transformed API data."""
    receiver, created = Receiver.objects.update_or_create(
        api_device_id=api_device_id,
        manufacturer=manufacturer,
        defaults={
            "ip": transformed_data.get("ip", ""),
            "device_type": transformed_data.get("type", "unknown"),
            "name": transformed_data.get("name", ""),
            "firmware_version": transformed_data.get("firmware", ""),
            "is_active": True,
            "last_seen": timezone.now(),
        },
    )

    if created:
        logger.info("Created new receiver: %s (%s)", receiver.name, api_device_id)
    else:
        logger.debug("Updated receiver: %s", api_device_id)

    return receiver


def _update_channel_and_transmitter(receiver, channel_info, plugin, api_device_id):
    """Update channel and transmitter for a receiver."""
    channel_num = channel_info.get("channel", 0)
    tx_data = channel_info.get("tx")

    if not tx_data:
        return

    # Transform transmitter data
    transformed_tx = plugin.transform_transmitter_data(tx_data, channel_num)
    if not transformed_tx:
        return

    # Create/update Channel
    channel, ch_created = Channel.objects.update_or_create(
        receiver=receiver,
        channel_number=channel_num,
    )

    if ch_created:
        logger.info(
            "Created new channel %d for receiver %s",
            channel_num,
            receiver.name,
        )

    # Assign slot and update/create transmitter
    target_slot = _assign_transmitter_slot(channel, transformed_tx, api_device_id, channel_num)

    transmitter, _ = Transmitter.objects.update_or_create(
        channel=channel,
        defaults={
            "slot": target_slot,
            "battery": transformed_tx.get("battery", 255),
            "battery_charge": transformed_tx.get("battery_charge"),
            "audio_level": transformed_tx.get("audio_level", 0),
            "rf_level": transformed_tx.get("rf_level", 0),
            "frequency": transformed_tx.get("frequency", ""),
            "antenna": transformed_tx.get("antenna", ""),
            "tx_offset": transformed_tx.get("tx_offset", 255),
            "quality": transformed_tx.get("quality", 255),
            "runtime": transformed_tx.get("runtime", ""),
            "status": transformed_tx.get("status", ""),
            "name": transformed_tx.get("name", ""),
            "name_raw": transformed_tx.get("name_raw", ""),
        },
    )

    # Check for alerts on this transmitter
    check_transmitter_alerts(transmitter)


def _assign_transmitter_slot(channel, transformed_tx, api_device_id, channel_num):
    """Assign a slot to a transmitter, preferring existing slots or API-provided slots."""
    api_slot = transformed_tx.get("slot")

    # Try to find existing transmitter for this channel
    try:
        transmitter = Transmitter.objects.get(channel=channel)
        target_slot = transmitter.slot  # Keep existing slot
        logger.debug(
            "Reusing existing slot %d for %s channel %d",
            target_slot,
            api_device_id,
            channel_num,
        )
        return target_slot
    except Transmitter.DoesNotExist:
        # New transmitter - assign slot
        if api_slot is not None:
            target_slot = api_slot
        else:
            # Generate a deterministic slot based on receiver and channel
            # This ensures consistent slot assignment across restarts
            base_slot = hash(f"{channel.receiver.api_device_id}-{channel_num}")
            # Use positive modulo to get a reasonable slot range
            target_slot = abs(base_slot) % 10000

            # Check for collisions and increment if needed
            while Transmitter.objects.filter(slot=target_slot).exists():
                target_slot = (target_slot + 1) % 10000

            logger.info(
                "Assigned new slot %d for %s channel %d",
                target_slot,
                api_device_id,
                channel_num,
            )
        return target_slot


def _mark_offline_receivers(manufacturer, active_receiver_ids):
    """Mark receivers that are no longer in API data as offline."""
    offline_count = (
        Receiver.objects.filter(manufacturer=manufacturer)
        .exclude(id__in=active_receiver_ids)
        .filter(is_active=True)
        .update(is_active=False)
    )

    if offline_count > 0:
        logger.warning("Marked %d receivers as offline for %s", offline_count, manufacturer.name)

        # Check for offline alerts on all channels of offline receivers
        offline_receivers = Receiver.objects.filter(manufacturer=manufacturer, is_active=False)
        for receiver in offline_receivers:
            for channel in receiver.channels.all():
                check_device_offline_alerts(channel)
