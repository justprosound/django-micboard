"""
API views for the micboard app.
"""
import json
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from micboard.decorators import rate_limit_view

# Updated imports
from micboard.models import DiscoveredDevice, Group, MicboardConfig, Receiver
from micboard.shure_api_client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


@rate_limit_view(max_requests=120, window_seconds=60)  # 2 requests per second
def data_json(request):
    """API endpoint for device data, similar to micboard_json"""
    # Try to get fresh data from cache first
    cached_data = cache.get("micboard_device_data")
    if cached_data:
        return JsonResponse(cached_data)

    receivers_data = []
    # Query the new model structure
    for receiver in Receiver.objects.filter(is_active=True).prefetch_related(
        "channels__transmitter"
    ):
        receiver_entry = {
            "api_device_id": receiver.api_device_id,
            "ip": receiver.ip,
            "type": receiver.device_type,
            "name": receiver.name,
            "firmware": receiver.firmware_version,
            "is_active": receiver.is_active,
            "last_seen": receiver.last_seen.isoformat() if receiver.last_seen else None,
            "channels": [],
        }
        for channel in receiver.channels.all():
            channel_entry = {
                "channel_number": channel.channel_number,
            }
            if hasattr(channel, "transmitter"):
                transmitter = channel.transmitter
                channel_entry["transmitter"] = {
                    "slot": transmitter.slot,
                    "battery": transmitter.battery,
                    "battery_percentage": transmitter.battery_percentage,
                    "audio_level": transmitter.audio_level,
                    "rf_level": transmitter.rf_level,
                    "frequency": transmitter.frequency,
                    "antenna": transmitter.antenna,
                    "tx_offset": transmitter.tx_offset,
                    "quality": transmitter.quality,
                    "runtime": transmitter.runtime,
                    "status": transmitter.status,
                    "name": transmitter.name,
                    "name_raw": transmitter.name_raw,
                    "updated_at": transmitter.updated_at.isoformat(),
                }
            receiver_entry["channels"].append(channel_entry)
        receivers_data.append(receiver_entry)

    # Add offline devices if any
    # For now, skip

    discovered = []
    for disc in DiscoveredDevice.objects.all():
        discovered.append(
            {
                "ip": disc.ip,
                "type": disc.device_type,
                "channels": disc.channels,
            }
        )

    config = {}
    for conf in MicboardConfig.objects.all():
        config[conf.key] = conf.value

    groups = []
    for group in Group.objects.all():
        groups.append(
            {
                "group": group.group_number,
                "title": group.title,
                "slots": group.slots,  # This will need to be re-evaluated later
                "hide_charts": group.hide_charts,
            }
        )

    data = {
        "receivers": receivers_data,  # Changed from "devices" to "receivers"
        "url": request.build_absolute_uri("/"),  # Placeholder
        "gif": [],  # Placeholder
        "jpg": [],  # Placeholder
        "mp4": [],  # Placeholder
        "config": config,
        "discovered": discovered,
        "groups": groups,
    }

    return JsonResponse(data)


@method_decorator(csrf_exempt, name="dispatch")
class ConfigHandler(View):
    """Handle config updates"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            for key, value in data.items():
                MicboardConfig.objects.update_or_create(key=key, defaults={"value": str(value)})
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception(f"Config update error: {e}")
            return JsonResponse({"error": str(e)}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class GroupUpdateHandler(View):
    """Handle group updates"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            group_num = data.get("group")
            if group_num is not None:
                Group.objects.update_or_create(
                    group_number=group_num,
                    defaults={
                        "title": data.get("title", ""),
                        "slots": data.get("slots", []),  # This will need to be re-evaluated later
                        "hide_charts": data.get("hide_charts", False),
                    },
                )
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception(f"Group update error: {e}")
            return JsonResponse({"error": str(e)}, status=400)


@rate_limit_view(max_requests=5, window_seconds=60)  # Discovery is expensive
def api_discover(request):
    """Trigger device discovery via Shure System API"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        client = ShureSystemAPIClient()
        # Use get_devices() as it's the documented way to get discovered devices
        discovered_devices_data = client.get_devices()

        # Save discovered devices
        for device_data in discovered_devices_data:
            # The 'type' field from get_devices() might be nested or different.
            # Assuming 'type' is directly available or can be extracted.
            # Also, 'channel_count' might not be directly in the top-level device_data.
            # This part might need adjustment based on actual API response for get_devices.
            device_type = ShureSystemAPIClient._map_device_type(device_data.get("type", "unknown"))

            # Attempt to get channel_count from capabilities or other nested fields
            channels = 0
            if "capabilities" in device_data and isinstance(device_data["capabilities"], list):
                for capability in device_data["capabilities"]:
                    if capability.get("name") == "channels":
                        channels = capability.get("count", 0)
                        break

            DiscoveredDevice.objects.update_or_create(
                ip=device_data.get("ip_address", ""),  # Assuming ip_address is available
                defaults={
                    "device_type": device_type,
                    "channels": channels,
                },
            )

        return JsonResponse(
            {
                "success": True,
                "discovered_count": len(discovered_devices_data),
                "devices": discovered_devices_data,
            }
        )
    except Exception as e:
        logger.exception(f"Error discovering devices: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@rate_limit_view(max_requests=10, window_seconds=60)  # Limit refresh requests
def api_refresh(request):
    """Force refresh device data from Shure System API"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        client = ShureSystemAPIClient()
        # The poll_all_devices method now returns data in the new Receiver/Channel/Transmitter structure
        # This data is then processed by the management command's update_models
        # For api_refresh, we just need to trigger the polling and clear the cache.
        # The actual data update happens in the poll_devices management command.
        # So, we don't need to process the returned data here directly.
        _ = client.poll_all_devices()  # Call to trigger polling and model updates

        # Clear cache to force fresh data
        cache.delete("micboard_device_data")

        return JsonResponse(
            {
                "success": True,
                "message": "Polling triggered, data will be refreshed soon.",
                "timestamp": str(timezone.now()),
            }
        )
    except Exception as e:
        logger.exception(f"Error refreshing data: {e}")
        return JsonResponse({"error": str(e)}, status=500)
