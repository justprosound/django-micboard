"""
Django management command to poll wireless devices and broadcast updates.

This command continuously polls manufacturer APIs for device status updates
and broadcasts changes to WebSocket clients via Django Channels.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from micboard.alerts import check_device_offline_alerts, check_transmitter_alerts
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    Channel,
    Manufacturer,
    Receiver,
    Transmitter,
)
from micboard.serializers import serialize_receivers

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Poll wireless devices via manufacturer APIs and broadcast updates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--initial-poll-only",
            action="store_true",
            help="Perform initial poll and exit (no WebSocket)",
        )
        parser.add_argument(
            "--no-broadcast", action="store_true", help="Disable WebSocket broadcasting to frontend"
        )
        parser.add_argument(
            "--manufacturer",
            type=str,
            help="Poll only devices from specified manufacturer code",
        )

    def handle(self, *args, **options):
        initial_poll_only = options["initial_poll_only"]
        broadcast_to_frontend = not options["no_broadcast"]
        manufacturer_filter = options.get("manufacturer")

        # Inactivity threshold (seconds) to close a session if no samples received
        self.inactivity_seconds = getattr(
            __import__("django.conf").conf.settings, "MICBOARD_CONFIG", {}
        ).get("TRANSMITTER_INACTIVITY_SECONDS", 10)

        # Cache configuration for in-memory session tracking
        self.session_cache_prefix = "micboard_tx_session_"
        # Keep session state in cache for a day by default
        self.session_cache_timeout = max(self.inactivity_seconds * 20, 60)

        self.stdout.write(
            self.style.SUCCESS(
                "Starting device management via manufacturer APIs (initial poll + WebSocket subscriptions)"
            )
        )

        channel_layer = get_channel_layer() if broadcast_to_frontend else None

        if not broadcast_to_frontend:
            self.stdout.write("Broadcasting disabled.")

        # Get manufacturers to poll
        if manufacturer_filter:
            try:
                manufacturers = [Manufacturer.objects.get(code=manufacturer_filter)]
                self.stdout.write(f"Polling only manufacturer: {manufacturer_filter}")
            except Manufacturer.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"Manufacturer '{manufacturer_filter}' not found")
                )
                return
        else:
            manufacturers = Manufacturer.objects.all()
            self.stdout.write(f"Polling {manufacturers.count()} manufacturers")

        # Initialize plugins for each manufacturer
        manufacturer_plugins = {}
        for manufacturer in manufacturers:
            try:
                plugin_class = get_manufacturer_plugin(manufacturer.code)
                plugin = plugin_class(manufacturer)
                manufacturer_plugins[manufacturer] = plugin
                self.stdout.write(f"Initialized plugin for {manufacturer.name}")
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Failed to initialize plugin for {manufacturer.name}: {e}")
                )
                continue

        if not manufacturer_plugins:
            self.stderr.write(self.style.ERROR("No manufacturer plugins could be initialized"))
            return

        # --- Initial Data Load (Polling) ---
        self.stdout.write(self.style.SUCCESS("Performing initial data poll..."))
        total_devices = 0
        for manufacturer, plugin in manufacturer_plugins.items():
            try:
                self.stdout.write(f"Polling {manufacturer.name} devices...")
                api_data = plugin.get_devices()
                if api_data:
                    device_count = self.update_models(api_data, manufacturer, plugin)
                    total_devices += device_count
                    self.stdout.write(f"Polled {device_count} devices from {manufacturer.name}")
                else:
                    self.stdout.write(
                        self.style.WARNING(f"No device data received from {manufacturer.name}")
                    )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"Initial poll failed for {manufacturer.name}: {exc}")
                )
                logger.exception("Initial polling error for %s", manufacturer.name)

        if total_devices > 0:
            if channel_layer:
                serialized_data = self.serialize_for_broadcast()
                async_to_sync(channel_layer.group_send)(
                    "micboard_updates",
                    {"type": "device_update", "data": serialized_data},
                )
        else:
            self.stdout.write(
                self.style.WARNING("No initial device data received from any manufacturer.")
            )

        if initial_poll_only:
            self.stdout.write(self.style.SUCCESS("Initial poll complete. Exiting."))
            return

        self.stdout.write(
            self.style.SUCCESS("Starting WebSocket subscriptions for active receivers...")
        )

        # --- WebSocket Subscriptions ---
        # This part will run indefinitely, managing WebSocket connections
        # For simplicity, each receiver gets its own WebSocket connection in a separate thread.
        # A more advanced solution would use a single WebSocket connection for multiple subscriptions.

        websocket_threads = []
        for manufacturer, plugin in manufacturer_plugins.items():
            for receiver in Receiver.objects.filter(manufacturer=manufacturer, is_active=True):
                thread = threading.Thread(
                    target=self._run_websocket_subscription,
                    args=(plugin, receiver.api_device_id, channel_layer, broadcast_to_frontend),
                    daemon=True,  # Allow main program to exit even if threads are running
                )
                websocket_threads.append(thread)
                thread.start()
                self.stdout.write(
                    f"Started WebSocket subscription thread for {manufacturer.name} {receiver.api_device_id}"
                )

        # Keep the main thread alive to allow daemon threads to run
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Polling interrupted by user. Exiting."))
            # Daemon threads will be terminated when main thread exits

    def _run_websocket_subscription(
        self,
        plugin,
        api_device_id: str,
        channel_layer,
        broadcast_to_frontend: bool,
    ):
        """Runs an asyncio event loop for a single WebSocket subscription."""

        async def subscribe_and_listen():
            try:
                await plugin.connect_and_subscribe(
                    api_device_id, self._websocket_callback(channel_layer, broadcast_to_frontend)
                )
            except Exception as exc:
                logger.exception("WebSocket subscription for %s failed: %s", api_device_id, exc)

        asyncio.run(subscribe_and_listen())

    def _websocket_callback(self, channel_layer, broadcast_to_frontend: bool):
        """Returns a callback function for WebSocket messages."""

        def callback(message_data: dict):
            logger.info(
                "Received WebSocket update for %s: %s",
                message_data.get("envelope", {}).get("deviceId"),
                message_data,
            )
            # Process the WebSocket message and update models
            # This part needs to be carefully implemented based on manufacturer API WebSocket message format
            # For now, let's assume the message_data contains enough info to update a Transmitter

            # Example: Assuming message_data contains 'envelope' and 'payload'
            envelope = message_data.get("envelope", {})
            payload = message_data.get("payload", {})

            device_id = envelope.get("deviceId")
            channel_num = payload.get("channel")  # Assuming channel info is in payload

            if device_id and channel_num is not None:
                try:
                    receiver = Receiver.objects.get(api_device_id=device_id)
                    channel = Channel.objects.get(receiver=receiver, channel_number=channel_num)
                    transmitter, _ = Transmitter.objects.get_or_create(channel=channel)

                    # Update transmitter fields based on payload
                    # This mapping needs to be precise based on manufacturer API WebSocket payload structure
                    transmitter.battery = payload.get("battery_bars", transmitter.battery)
                    transmitter.audio_level = payload.get("audio_level", transmitter.audio_level)
                    transmitter.rf_level = payload.get("rf_level", transmitter.rf_level)
                    transmitter.status = payload.get("status", transmitter.status)
                    transmitter.updated_at = timezone.now()
                    transmitter.save()

                    logger.info(
                        "Updated Transmitter for %s Channel %s from WebSocket.",
                        device_id,
                        channel_num,
                    )

                    # Broadcast update to frontend
                    if channel_layer and broadcast_to_frontend:
                        serialized_data = (
                            self.serialize_for_broadcast()
                        )  # Re-serialize all active devices
                        async_to_sync(channel_layer.group_send)(
                            "micboard_updates",
                            {"type": "device_update", "data": serialized_data},
                        )

                except Receiver.DoesNotExist:
                    logger.warning("Receiver %s not found for WebSocket update.", device_id)
                except Channel.DoesNotExist:
                    logger.warning(
                        "Channel %s not found for Receiver %s for WebSocket update.",
                        channel_num,
                        device_id,
                    )
                except Exception:
                    logger.exception("Error processing WebSocket message for %s", device_id)
            else:
                logger.warning("WebSocket message missing deviceId or channel: %s", message_data)

        return callback

    def update_models(self, api_data, manufacturer, plugin):
        """Update Django models with API data and handle slot assignment intelligently"""
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
                active_receiver_ids.append(receiver.id)

                if created:
                    logger.info("Created new receiver: %s (%s)", receiver.name, api_device_id)
                else:
                    logger.debug("Updated receiver: %s", api_device_id)

                # Update channels and transmitters
                channels_data = plugin.get_device_channels(api_device_id)
                for channel_info in channels_data:
                    channel_num = channel_info.get("channel", 0)
                    tx_data = channel_info.get("tx")

                    if tx_data:
                        # Transform transmitter data
                        transformed_tx = plugin.transform_transmitter_data(tx_data, channel_num)
                        if not transformed_tx:
                            continue

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

                        # Intelligent slot assignment
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
                        except Transmitter.DoesNotExist:
                            # New transmitter - assign slot
                            if api_slot is not None:
                                target_slot = api_slot
                            else:
                                # Generate a deterministic slot based on receiver and channel
                                # This ensures consistent slot assignment across restarts
                                base_slot = hash(f"{receiver.api_device_id}-{channel_num}")
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

                        # Update or create transmitter with all fields
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

                        # Track session & samples
                        self._record_sample_and_session(transmitter, transformed_tx)
                updated_count += 1

            except Exception:
                logger.exception("Error updating device %s", api_device_id)
                continue

        # Mark receivers that were not in the API data as offline
        offline_count = (
            Receiver.objects.filter(manufacturer=manufacturer)
            .exclude(id__in=active_receiver_ids)
            .filter(is_active=True)
            .update(is_active=False)
        )

        if offline_count > 0:
            logger.warning(
                "Marked %d receivers as offline for %s", offline_count, manufacturer.name
            )

            # Check for offline alerts on all channels of offline receivers
            offline_receivers = Receiver.objects.filter(manufacturer=manufacturer, is_active=False)
            for receiver in offline_receivers:
                for channel in receiver.channels.all():
                    check_device_offline_alerts(channel)

        return updated_count

    def serialize_for_broadcast(self):
        """
        Serialize all active receiver, channel, and transmitter data for WebSocket transmission.

        Uses the centralized serializers module for consistent data structure.
        """
        return {"receivers": serialize_receivers(include_extra=False)}

    # --- Session & Sample Tracking (Cache-based, no DB persistence) ---
    def _session_cache_key(self, slot: int) -> str:
        return f"{self.session_cache_prefix}{slot}"

    def _get_active_session(self, slot: int) -> dict[str, Any] | None:
        session = cache.get(self._session_cache_key(slot))
        if session and isinstance(session, dict) and session.get("is_active"):
            return session  # type: ignore
        return None

    def _start_session(self, transmitter: Transmitter, status: str) -> dict:
        now = timezone.now()
        session = {
            "slot": transmitter.slot,
            "receiver": transmitter.channel.receiver.name,
            "channel": transmitter.channel.channel_number,
            "started_at": now,
            "last_seen": now,
            "ended_at": None,
            "is_active": True,
            "last_status": status or "",
            "sample_count": 0,
            # small rolling buffer of last samples for debugging/diagnostics
            "samples": [],
        }
        cache.set(
            self._session_cache_key(transmitter.slot), session, timeout=self.session_cache_timeout
        )
        logger.info(
            "Transmitter active: slot=%s, receiver=%s, channel=%s",
            transmitter.slot,
            session["receiver"],
            session["channel"],
        )
        return session

    def _end_session(self, session: dict) -> None:
        if not session.get("is_active"):
            return
        session["is_active"] = False
        session["ended_at"] = timezone.now()
        cache.set(
            self._session_cache_key(session["slot"]), session, timeout=self.session_cache_timeout
        )
        duration = int((session["ended_at"] - session["started_at"]).total_seconds())
        logger.info(
            "Transmitter inactive: slot=%s, duration=%ss, samples=%s",
            session["slot"],
            duration,
            session.get("sample_count", 0),
        )

    def _record_sample_and_session(self, transmitter: Transmitter, tx_data: dict) -> None:
        """Record a sample in cache, manage session lifecycle, and detect outages."""
        now = timezone.now()
        session = self._get_active_session(transmitter.slot)

        if session is None:
            # Start a new session on first sample
            session = self._start_session(transmitter, tx_data.get("status", ""))
        else:
            # If inactive for longer than threshold, close old and start new
            gap = (now - session["last_seen"]).total_seconds()
            if gap > self.inactivity_seconds:
                logger.warning(
                    "Short outage detected: slot=%s gap=%ss (> %ss)",
                    transmitter.slot,
                    int(gap),
                    self.inactivity_seconds,
                )
                self._end_session(session)
                session = self._start_session(transmitter, tx_data.get("status", ""))

        # Record sample (rolling buffer up to 100 most-recent samples)
        sample = {
            "timestamp": now.isoformat(),
            "battery": tx_data.get("battery"),
            "battery_charge": tx_data.get("battery_charge"),
            "audio_level": tx_data.get("audio_level"),
            "rf_level": tx_data.get("rf_level"),
            "quality": tx_data.get("quality"),
            "status": tx_data.get("status", ""),
            "frequency": str(tx_data.get("frequency", "")),
        }
        session["samples"].append(sample)
        if len(session["samples"]) > 100:
            session["samples"] = session["samples"][-100:]

        session["sample_count"] = session.get("sample_count", 0) + 1
        session["last_seen"] = now
        session["last_status"] = tx_data.get("status", session.get("last_status", ""))

        cache.set(
            self._session_cache_key(transmitter.slot), session, timeout=self.session_cache_timeout
        )
