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
from micboard.serializers import (
    serialize_discovered_device,
    serialize_group,
    serialize_receiver_detail,
    serialize_receiver_summary,
    serialize_receivers,
)
from micboard.shure_api_client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


@rate_limit_view(max_requests=120, window_seconds=60)  # 2 requests per second
def data_json(request):
    """API endpoint for device data, similar to micboard_json"""
    try:
        # Try to get fresh data from cache first
        cached_data = cache.get("micboard_device_data")
        if cached_data:
            return JsonResponse(cached_data)

        # Use serializer for consistent data structure
        receivers_data = serialize_receivers(include_extra=True)

        # Serialize discovered devices
        discovered = [
            serialize_discovered_device(disc) for disc in DiscoveredDevice.objects.all()
        ]

        # Serialize config
        config = {conf.key: conf.value for conf in MicboardConfig.objects.all()}

        # Serialize groups
        groups = [serialize_group(group) for group in Group.objects.all()]

        data = {
            "receivers": receivers_data,
            "url": request.build_absolute_uri("/"),
            "gif": [],  # Placeholder for future media support
            "jpg": [],  # Placeholder for future media support
            "mp4": [],  # Placeholder for future media support
            "config": config,
            "discovered": discovered,
            "groups": groups,
        }

        return JsonResponse(data)
    except Exception as e:
        logger.exception(f"Error fetching device data: {e}")
        return JsonResponse({"error": "Internal server error", "detail": str(e)}, status=500)


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


@rate_limit_view(max_requests=30, window_seconds=60)
def api_health(request):
    """Health check endpoint for the API and Shure System connectivity"""
    try:
        client = ShureSystemAPIClient()
        health_info = {
            "api_status": "healthy",
            "timestamp": timezone.now().isoformat(),
            "database": {
                "receivers_total": Receiver.objects.count(),
                "receivers_active": Receiver.objects.active().count(),
                "receivers_healthy": Receiver.objects.filter(is_active=True).count(),
            },
        }

        # Check Shure API health
        try:
            api_healthy = client.is_healthy()
            health_info["shure_api"] = {
                "status": "healthy" if api_healthy else "degraded",
                "healthy": api_healthy,
            }
        except Exception as e:
            logger.warning(f"Shure API health check failed: {e}")
            health_info["shure_api"] = {"status": "unavailable", "error": str(e)}

        return JsonResponse(health_info)
    except Exception as e:
        logger.exception(f"Health check error: {e}")
        return JsonResponse({"error": "Health check failed", "detail": str(e)}, status=500)


@rate_limit_view(max_requests=60, window_seconds=60)
def api_receiver_detail(request, receiver_id):
    """Get detailed information for a specific receiver"""
    try:
        receiver = Receiver.objects.prefetch_related("channels__transmitter").get(
            api_device_id=receiver_id
        )
        data = serialize_receiver_detail(receiver)
        return JsonResponse(data)
    except Receiver.DoesNotExist:
        return JsonResponse({"error": "Receiver not found"}, status=404)
    except Exception as e:
        logger.exception(f"Error fetching receiver detail: {e}")
        return JsonResponse({"error": "Internal server error", "detail": str(e)}, status=500)


@rate_limit_view(max_requests=60, window_seconds=60)
def api_receivers_list(request):
    """Get list of all receivers with basic information"""
    try:
        receivers = [
            serialize_receiver_summary(receiver)
            for receiver in Receiver.objects.all().order_by("name")
        ]
        return JsonResponse({"receivers": receivers, "count": len(receivers)})
    except Exception as e:
        logger.exception(f"Error fetching receivers list: {e}")
        return JsonResponse({"error": "Internal server error", "detail": str(e)}, status=500)

