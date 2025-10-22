"""
Request-related signal handlers for the micboard app.
"""

# Request-related signal handlers for the micboard app.
from __future__ import annotations

import logging

from django.dispatch import Signal, receiver
from django.utils import timezone

from micboard.discovery.service import DiscoveryService
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    DiscoveredDevice,
    Manufacturer,
    Receiver,
)
from micboard.serializers import ReceiverSummarySerializer
from micboard.signals.broadcast_signals import devices_polled

logger = logging.getLogger(__name__)

# Signals to request discovery or refresh across manufacturers. Views emit these
# signals and handlers do the heavy work.
discover_requested = Signal()
refresh_requested = Signal()
device_detail_requested = Signal()
add_discovery_ips_requested = Signal()
# Signal to request the current candidate discovery IP list for a manufacturer.
# Handlers should return a dict mapping manufacturer_code -> {'ips': [..]}
discovery_candidates_requested = Signal()


@receiver(discover_requested)
def handle_discover_requested(
    sender, *, manufacturer: str | None = None, request=None, **kwargs
) -> dict[str, dict]:
    """Handle discover requests by calling each manufacturer's plugin.get_devices.

    Returns a mapping of manufacturer_code -> {status, count, devices|error}
    """
    results: dict[str, dict] = {}
    try:
        if manufacturer:
            manufacturers = Manufacturer.objects.filter(code=manufacturer)
        else:
            manufacturers = Manufacturer.objects.all()

        for m in manufacturers:
            try:
                plugin_cls = get_manufacturer_plugin(m.code)
                plugin = plugin_cls(m)
                devices = plugin.get_devices() or []

                # Persist discovered devices summary
                for device_data in devices:
                    transformed = plugin.transform_device_data(device_data)
                    if not transformed:
                        continue
                    DiscoveredDevice.objects.update_or_create(
                        ip=transformed.get("ip", ""),
                        manufacturer=m,
                        defaults={
                            "device_type": transformed.get("type", "unknown"),
                            "channels": len(transformed.get("channels", [])),
                        },
                    )

                results[m.code] = {"status": "success", "count": len(devices), "devices": devices}
            except Exception as exc:
                logger.exception("Discovery error for %s: %s", m.code, exc)
                results[m.code] = {"status": "error", "error": str(exc)}
    except Exception:
        logger.exception("Unhandled error in discover_requested handler")
    return results


@receiver(refresh_requested)
def handle_refresh_requested(
    sender, *, manufacturer: str | None = None, request=None, **kwargs
) -> dict[str, dict]:
    """Handle refresh requests by polling detailed data and broadcasting updates.

    Returns a mapping of manufacturer_code -> {status, device_count, updated}
    """
    results: dict[str, dict] = {}
    try:
        if manufacturer:
            manufacturers = Manufacturer.objects.filter(code=manufacturer)
        else:
            manufacturers = Manufacturer.objects.all()

        for m in manufacturers:
            try:
                plugin_cls = get_manufacturer_plugin(m.code)
                plugin = plugin_cls(m)

                updated = 0
                devices_data = plugin.get_devices() or []

                # Update models for each device
                for dev in devices_data:
                    device_id = dev.get("id") or dev.get("api_device_id")
                    if not device_id:
                        continue

                    full = plugin.get_device(device_id) or dev
                    # Enrich with channels
                    try:
                        channels = plugin.get_device_channels(device_id)
                        full["channels"] = channels
                    except Exception:
                        logger.debug("No channel data for %s", device_id)

                    transformed = plugin.transform_device_data(full)
                    if not transformed:
                        continue

                    # Update Receiver and slots via existing poll logic: reuse update if possible
                    try:
                        _rx, _created = Receiver.objects.update_or_create(
                            api_device_id=transformed.get("api_device_id") or transformed.get("id"),
                            manufacturer=m,
                            defaults={
                                "ip": transformed.get("ip", ""),
                                "device_type": transformed.get("type", "unknown"),
                                "name": transformed.get("name", ""),
                                "firmware_version": transformed.get("firmware", ""),
                                "is_active": True,
                                "last_seen": timezone.now(),
                            },
                        )
                        updated += 1
                    except Exception:
                        logger.exception("Failed to update Receiver for %s", device_id)
                        continue

                # Broadcast updated list via devices_polled signal
                try:
                    # Use the new DRF serializer
                    data = {
                        "receivers": ReceiverSummarySerializer(
                            Receiver.objects.filter(manufacturer=m), many=True
                        ).data
                    }
                    devices_polled.send(handle_refresh_requested, manufacturer=m, data=data)
                except Exception:
                    logger.debug("Failed to emit devices_polled after refresh for %s", m.code)

                results[m.code] = {
                    "status": "success",
                    "device_count": len(devices_data),
                    "updated": updated,
                }
            except Exception as exc:
                logger.exception("Refresh error for %s: %s", m.code, exc)
                results[m.code] = {"status": "error", "error": str(exc)}
    except Exception:
        logger.exception("Unhandled error in refresh_requested handler")
    return results


@receiver(device_detail_requested)
def handle_device_detail_requested(
    sender,
    *,
    manufacturer: str | None = None,
    device_id: str | None = None,
    request=None,
    **kwargs,
) -> dict:
    """Fetch a single device's detailed data across manufacturer plugins, returning transformed data."""
    if not device_id:
        return {"status": "error", "error": "device_id required"}

    try:
        if manufacturer:
            manufacturers = Manufacturer.objects.filter(code=manufacturer)
        else:
            manufacturers = Manufacturer.objects.all()

        for m in manufacturers:
            try:
                plugin_cls = get_manufacturer_plugin(m.code)
                plugin = plugin_cls(m)
                dev = plugin.get_device(device_id)
                if not dev:
                    continue

                # Enrich with channels
                try:
                    channels = plugin.get_device_channels(device_id)
                    dev["channels"] = channels
                except Exception:
                    logger.debug("No channel data for %s", device_id)

                transformed = plugin.transform_device_data(dev)
                return {m.code: {"status": "success", "device": transformed}}
            except Exception as exc:
                logger.exception("Error fetching device %s for %s: %s", device_id, m.code, exc)
                return {m.code: {"status": "error", "error": str(exc)}}
    except Exception:
        logger.exception("Unhandled error in device_detail_requested handler")
        return {"status": "error", "error": "unhandled error"}
    # No device found across manufacturers
    return {"status": "error", "error": "device not found"}


@receiver(add_discovery_ips_requested)
def handle_add_discovery_ips_requested(
    sender,
    *,
    manufacturer: str | None = None,
    ips: list | None = None,
    request=None,
    **kwargs,
) -> dict:
    """Add IPs to a manufacturer's discovery list via the DiscoveryService."""
    if not ips:
        return {"status": "error", "error": "ips required"}
    try:
        results = {}
        discovery_service = DiscoveryService()
        if manufacturer:
            manufacturers = Manufacturer.objects.filter(code=manufacturer)
        else:
            manufacturers = Manufacturer.objects.all()

        for m in manufacturers:
            successful_adds = 0
            for ip in ips:
                if discovery_service.add_discovery_candidate(ip, m, source="manual_request"):
                    successful_adds += 1
            results[m.code] = {"status": "success", "added_count": successful_adds}
        return results
    except Exception:
        logger.exception("Unhandled error in add_discovery_ips_requested handler")
        return {"status": "error", "error": "unhandled"}


@receiver(discovery_candidates_requested)
def handle_discovery_candidates_requested(
    sender, *, manufacturer: str | None = None, **kwargs
) -> dict:
    """Return candidate discovery IPs for manufacturers using DiscoveryService."""
    results: dict[str, dict] = {}
    try:
        discovery_service = DiscoveryService()
        if manufacturer:
            manufacturers = Manufacturer.objects.filter(code=manufacturer)
        else:
            manufacturers = Manufacturer.objects.all()

        for m in manufacturers:
            try:
                # Use the discovery service to get candidates
                ips = discovery_service._get_manufacturer_client(m).get_discovery_ips()
                results[m.code] = {"status": "success", "ips": ips}
            except Exception as exc:
                logger.exception("Error computing discovery candidates for %s: %s", m.code, exc)
                results[m.code] = {"status": "error", "error": str(exc)}
    except Exception:
        logger.exception("Unhandled error in discovery_candidates_requested handler")
    return results
