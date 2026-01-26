"""Polling-related background tasks for the micboard app.

NOTE: This module is being refactored to use the new service layer.
New code should use PollingService directly. These tasks are maintained
for backwards compatibility with existing celery/django-q configurations.
"""

# Polling-related background tasks for the micboard app.
from __future__ import annotations

import logging

from django.utils import timezone

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    Manufacturer,
    RFChannel,
    WirelessChassis,
    WirelessUnit,
)
from micboard.serializers import ReceiverSummarySerializer
from micboard.services.alerts import check_device_offline_alerts, check_transmitter_alerts
from micboard.signals.broadcast_signals import api_health_changed, devices_polled

logger = logging.getLogger(__name__)


def poll_manufacturer_devices(manufacturer_id: int):
    """Task to poll devices for a specific manufacturer and update models.

    NOTE: This is a legacy task wrapper. New code should use:
        from micboard.services import PollingService
        service = PollingService()
        service.poll_manufacturer(manufacturer)
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)

        # Use the new PollingService for clean service-based approach
        from micboard.services import PollingService

        service = PollingService()
        result = service.poll_manufacturer(manufacturer)

        # Run alerts after polling
        check_device_offline_alerts()
        check_transmitter_alerts()

        logger.info(
            "Polling task complete for %s: %d devices created/updated, %d transmitters",
            manufacturer.name,
            result.get("devices_created", 0) + result.get("devices_updated", 0),
            result.get("transmitters_synced", 0),
        )

        # Start real-time subscriptions
        _start_realtime_subscriptions(manufacturer)

        return result

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for device polling task.", manufacturer_id
        )
    except Exception as e:
        logger.exception("Error polling devices for manufacturer ID %s: %s", manufacturer_id, e)


def poll_manufacturer_devices_legacy(manufacturer_id: int):
    """DEPRECATED: Legacy polling implementation kept for reference.
    Use poll_manufacturer_devices() instead, which uses PollingService.
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
                    WirelessChassis.objects.filter(manufacturer=manufacturer), many=True
                ).data
            }
            devices_polled.send(sender=None, manufacturer=manufacturer, data=serialized_data)

            # Start real-time subscriptions for this manufacturer
            _start_realtime_subscriptions(manufacturer)
        else:
            logger.warning("No device data received from %s", manufacturer.name)

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for device polling task.", manufacturer_id
        )
    except Exception as e:
        logger.exception("Error polling devices for manufacturer ID %s: %s", manufacturer_id, e)


def _update_models_from_api_data(api_data, manufacturer, plugin):
    """Helper function to update Django models with API data.
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
    from micboard.services.device_lifecycle import get_lifecycle_manager

    receiver, created = WirelessChassis.objects.update_or_create(
        api_device_id=api_device_id,
        manufacturer=manufacturer,
        defaults={
            "ip": transformed_data.get("ip", ""),
            "device_type": transformed_data.get("type", "unknown"),
            "name": transformed_data.get("name", ""),
            "firmware_version": transformed_data.get("firmware", ""),
            "last_seen": timezone.now(),
        },
    )

    # Use lifecycle manager for state transition
    lifecycle = get_lifecycle_manager(manufacturer.code)
    if created:
        logger.info("Created new receiver: %s (%s)", receiver.name, api_device_id)
        lifecycle.mark_online(receiver)
    else:
        logger.debug("Updated receiver: %s", api_device_id)
        # Only transition to online if not in a stable state
        if receiver.status not in {"online", "degraded", "maintenance"}:
            lifecycle.mark_online(receiver)

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
    channel, ch_created = RFChannel.objects.update_or_create(
        chassis=receiver,
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

    transmitter, _ = WirelessUnit.objects.update_or_create(
        assigned_resource=channel,
        defaults={
            "slot": target_slot,
            "manufacturer": receiver.manufacturer,
            "base_chassis": receiver,
            "battery": transformed_tx.get("battery", 255),
            "battery_charge": transformed_tx.get("battery_charge"),
            "audio_level": transformed_tx.get("audio_level", 0),
            "rf_level": transformed_tx.get("rf_level", 0),
            "frequency": transformed_tx.get("frequency", ""),
            "antenna": transformed_tx.get("antenna", ""),
            "tx_offset": transformed_tx.get("tx_offset", 255),
            "quality": transformed_tx.get("quality", 255),
            "battery_runtime": transformed_tx.get("runtime", ""),
            "status": transformed_tx.get("status", ""),
            "name": transformed_tx.get("name", ""),
        },
    )

    # Check for alerts on this transmitter
    check_transmitter_alerts(transmitter)


def _assign_transmitter_slot(channel, transformed_tx, api_device_id, channel_num):
    """Assign a slot to a transmitter, preferring existing slots or API-provided slots."""
    api_slot = transformed_tx.get("slot")

    # Try to find existing transmitter for this channel
    try:
        transmitter = WirelessUnit.objects.get(assigned_resource=channel)
        target_slot = transmitter.slot  # Keep existing slot
        logger.debug(
            "Reusing existing slot %d for %s channel %d",
            target_slot,
            api_device_id,
            channel_num,
        )
        return target_slot
    except WirelessUnit.DoesNotExist:
        # New transmitter - assign slot
        if api_slot is not None:
            target_slot = api_slot
        else:
            # Generate a deterministic slot based on receiver and channel
            # This ensures consistent slot assignment across restarts
            base_slot = hash(f"{channel.chassis.api_device_id}-{channel_num}")
            # Use positive modulo to get a reasonable slot range
            target_slot = abs(base_slot) % 10000

            # Check for collisions and increment if needed
            while WirelessUnit.objects.filter(slot=target_slot).exists():
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
    from micboard.services.device_lifecycle import get_lifecycle_manager

    # Find receivers that should be marked offline
    offline_receivers = WirelessChassis.objects.filter(
        manufacturer=manufacturer, status__in={"online", "degraded", "provisioning"}
    ).exclude(id__in=active_receiver_ids)

    if not offline_receivers.exists():
        return

    lifecycle = get_lifecycle_manager(manufacturer.code)
    offline_count = 0

    for receiver in offline_receivers:
        try:
            lifecycle.mark_offline(receiver, reason="Device not found in API poll")
            offline_count += 1
        except Exception:
            logger.exception("Error marking receiver %s as offline", receiver.id)

    if offline_count > 0:
        logger.warning("Marked %d receivers as offline for %s", offline_count, manufacturer.name)

        # Check for offline alerts on all channels of offline receivers
        offline_receivers_refreshed = WirelessChassis.objects.filter(
            manufacturer=manufacturer, status="offline"
        )
        for receiver in offline_receivers_refreshed:
            for channel in receiver.rf_channels.all():
                check_device_offline_alerts(channel)


def _start_realtime_subscriptions(manufacturer):
    """Start real-time subscriptions for a manufacturer."""
    try:
        from django_q.tasks import async_task

        if manufacturer.code == "shure":
            # Start WebSocket subscriptions for Shure
            from micboard.tasks.websocket_tasks import start_shure_websocket_subscriptions

            async_task(start_shure_websocket_subscriptions)
            logger.info("Started WebSocket subscriptions for %s", manufacturer.name)
        elif manufacturer.code == "sennheiser":
            # Start SSE subscriptions for Sennheiser
            from micboard.tasks.sse_tasks import start_sse_subscriptions

            async_task(start_sse_subscriptions, manufacturer.id)
            logger.info("Started SSE subscriptions for %s", manufacturer.name)
        else:
            logger.debug("No real-time subscriptions available for %s", manufacturer.code)

    except Exception as e:
        logger.exception("Error starting real-time subscriptions for %s: %s", manufacturer.name, e)
