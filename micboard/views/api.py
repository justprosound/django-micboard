"""
API views for the micboard app.
"""

import json
import logging

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
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
from micboard.shure import ShureSystemAPIClient
from micboard.shure.transformers import ShureDataTransformer

logger = logging.getLogger(__name__)


class APIView(View):
    """
    Base API view class that adds version headers and common API functionality.

    This provides a foundation for versioned API responses and consistent
    behavior across all API endpoints.
    """

    API_VERSION = "1.0.0"

    def dispatch(self, request, *args, **kwargs):
        """Add API version headers to all responses."""
        response = super().dispatch(request, *args, **kwargs)

        # Add version headers
        response["X-API-Version"] = self.API_VERSION
        response["X-API-Compatible"] = "1.0.0"

        # Add content type if not set
        if not response.get("Content-Type"):
            response["Content-Type"] = "application/json"

        return response


class VersionedAPIView(APIView):
    """
    Extended API view that supports version negotiation.

    This can be used for future API versions that need different behavior.
    """

    def get_api_version(self, request: HttpRequest) -> str:
        """Determine API version from request."""
        # Check Accept header for version
        accept = request.META.get("HTTP_ACCEPT", "")
        if "version=" in accept:
            # Extract version from Accept: application/json; version=1.1
            try:
                version_part = accept.split("version=")[1].split(";")[0]
                return version_part.strip()
            except (IndexError, ValueError):
                pass

        # Check query parameter
        version = request.GET.get("version")
        if version:
            return version

        # Default to current version
        return self.API_VERSION


@rate_limit_view(max_requests=120, window_seconds=60)  # 2 requests per second
@cache_page(30)  # Cache for 30 seconds
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
        discovered = [serialize_discovered_device(disc) for disc in DiscoveredDevice.objects.all()]

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
class ConfigHandler(VersionedAPIView):
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
class GroupUpdateHandler(VersionedAPIView):
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
            device_type = ShureDataTransformer._map_device_type(device_data.get("type", "unknown"))

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
            client = ShureSystemAPIClient()
            api_healthy = client.is_healthy()
            health_info["shure_api"] = {
                "status": "healthy" if api_healthy else "degraded",
                "healthy": api_healthy,
            }
        except Exception as e:
            logger.warning(f"Shure API health check failed: {e}")
            health_info["shure_api"] = {"status": "unavailable", "error": str(e)}
            health_info["api_status"] = "degraded"  # API issues make overall status degraded

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


class HealthCheckView(VersionedAPIView):
    """Health check endpoint for monitoring service status."""

    def get(self, request):
        """Return health status of the service and its dependencies."""
        health_status = {
            "status": "healthy",
            "timestamp": timezone.now().isoformat(),
            "version": "25.10.15",
            "api_version": self.get_api_version(request),
            "checks": {},
        }

        # Database check
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status["checks"]["database"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "unhealthy"

        # Cache check
        try:
            cache.set("health_check", "ok", 10)
            cache_value = cache.get("health_check")
            if cache_value == "ok":
                health_status["checks"]["cache"] = {"status": "healthy"}
            else:
                health_status["checks"]["cache"] = {
                    "status": "unhealthy",
                    "error": "Cache not working",
                }
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["checks"]["cache"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "unhealthy"

        # Shure API check
        try:
            client = ShureSystemAPIClient()
            # Just check if we can create a client, don't actually call API
            health_status["checks"]["shure_api_client"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["shure_api_client"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"  # API issues don't make service unhealthy

        status_code = 200 if health_status["status"] == "healthy" else 503
        return JsonResponse(health_status, status=status_code)


class ReadinessCheckView(VersionedAPIView):
    """Readiness check endpoint for Kubernetes/load balancer health checks."""

    def get(self, request):
        """Return readiness status - simplified check for load balancers."""
        try:
            # Quick database check
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            return JsonResponse(
                {
                    "status": "ready",
                    "timestamp": timezone.now().isoformat(),
                    "api_version": self.get_api_version(request),
                }
            )
        except Exception as e:
            logger.exception("Readiness check failed")
            return JsonResponse(
                {
                    "status": "not ready",
                    "error": str(e),
                    "timestamp": timezone.now().isoformat(),
                    "api_version": self.get_api_version(request),
                },
                status=503,
            )


class APIDocumentationView(VersionedAPIView):
    """API documentation endpoint showing available endpoints and versions."""

    def get(self, request):
        """Return API documentation with available endpoints."""
        api_version = self.get_api_version(request)

        documentation = {
            "api_version": api_version,
            "app_version": "25.10.15",
            "base_url": request.build_absolute_uri("/api/"),
            "endpoints": {
                "health": {
                    "url": "/api/health/",
                    "method": "GET",
                    "description": "Basic health check",
                    "response": {
                        "status": "healthy|degraded",
                        "timestamp": "ISO 8601 timestamp",
                        "database": {"receivers_total": 0, "receivers_active": 0},
                        "shure_api": {"status": "healthy|unavailable"},
                    },
                },
                "health_detailed": {
                    "url": "/api/health/detailed/",
                    "method": "GET",
                    "description": "Detailed health check with all components",
                    "response": {
                        "status": "healthy|unhealthy|degraded",
                        "timestamp": "ISO 8601 timestamp",
                        "version": "app version",
                        "api_version": "API version",
                        "checks": {
                            "database": {"status": "healthy|unhealthy"},
                            "cache": {"status": "healthy|unhealthy"},
                            "shure_api_client": {"status": "healthy|unhealthy"},
                        },
                    },
                },
                "health_ready": {
                    "url": "/api/health/ready/",
                    "method": "GET",
                    "description": "Readiness check for load balancers",
                    "response": {
                        "status": "ready|not ready",
                        "timestamp": "ISO 8601 timestamp",
                        "api_version": "API version",
                    },
                },
                "data": {
                    "url": "/api/data.json",
                    "method": "GET",
                    "description": "Main data endpoint with receivers, groups, and config",
                    "response": {
                        "receivers": [],
                        "url": "base URL",
                        "config": {},
                        "discovered": [],
                        "groups": [],
                    },
                },
                "receivers": {
                    "url": "/api/receivers/",
                    "method": "GET",
                    "description": "List all receivers with summary information",
                    "response": {"receivers": [], "count": 0},
                },
                "receiver_detail": {
                    "url": "/api/receivers/{id}/",
                    "method": "GET",
                    "description": "Detailed information for a specific receiver",
                    "parameters": {"id": "Receiver ID"},
                    "response": {"api_device_id": "string", "name": "string", "channels": []},
                },
                "discover": {
                    "url": "/api/discover/",
                    "method": "POST",
                    "description": "Trigger device discovery on the network",
                    "response": {"success": True, "discovered_count": 0, "devices": []},
                },
                "refresh": {
                    "url": "/api/refresh/",
                    "method": "POST",
                    "description": "Force refresh of device data from Shure API",
                    "response": {"success": True, "message": "Polling triggered"},
                },
                "config": {
                    "url": "/api/config/",
                    "method": "GET|POST",
                    "description": "Get or update application configuration",
                    "response": {"success": True},
                },
                "group_update": {
                    "url": "/api/groups/{id}/",
                    "method": "POST",
                    "description": "Update group configuration",
                    "parameters": {"id": "Group ID"},
                    "response": {"success": True},
                },
            },
            "versions": {"current": "v1", "supported": ["v1"], "deprecated": []},
            "authentication": "None required",
            "rate_limiting": "Varies by endpoint (see decorators)",
            "content_type": "application/json",
            "versioning": {
                "url_path": "/api/v1/endpoint/",
                "query_param": "/api/endpoint/?version=v1",
                "accept_header": "Accept: application/json; version=1",
            },
        }

        return JsonResponse(documentation)
