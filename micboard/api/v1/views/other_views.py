import logging

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.utils import _get_manufacturer_code
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    DeviceAssignment,
    Manufacturer,
)
from micboard.serializers import (
    DeviceAssignmentSerializer,
)
from micboard.signals import refresh_requested

logger = logging.getLogger(__name__)


class APIDocumentationAPIView(APIView):
    """
    API documentation endpoint showing available endpoints and versions.
    """

    def get(self, request, *args, **kwargs):
        api_version = "1.0.0"  # TODO: Get from base_views or app config

        documentation = {
            "api_version": api_version,
            "app_version": "25.10.15",  # TODO: Get from app config
            "base_url": request.build_absolute_uri("/api/"),
            "endpoints": {
                "health": {
                    "url": "/api/health/",
                    "method": "GET",
                    "description": "Basic health check with manufacturer status",
                    "parameters": {"manufacturer": "Optional: Check specific manufacturer only"},
                    "response": {
                        "api_status": "healthy|degraded",
                        "timestamp": "ISO 8601 timestamp",
                        "database": {"receivers_total": 0, "receivers_active": 0},
                        "manufacturers": {"ManufacturerName": {"status": "healthy", "details": {}}},
                    },
                },
                "readiness": {
                    "url": "/api/health/ready/",
                    "method": "GET",
                    "description": "Readiness check for load balancers",
                    "response": {
                        "status": "ready|not ready",
                        "timestamp": "ISO 8601 timestamp",
                        "api_version": "API version",
                    },
                },
                # TODO: Add other endpoints as they are refactored
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

        return Response(documentation)


class RefreshAPIView(APIView):
    """
    API endpoint to force refresh device data from manufacturer APIs.
    Replaces micboard.api.core_views.api_refresh.
    """

    def post(self, request, *args, **kwargs):
        manufacturer_code = _get_manufacturer_code(request)

        refresh_results = {}
        total_devices = 0

        # Get manufacturers to refresh from
        if manufacturer_code:
            try:
                _ = Manufacturer.objects.get(code=manufacturer_code)
                manufacturers = [Manufacturer.objects.get(code=manufacturer_code)]
            except Manufacturer.DoesNotExist:
                return Response(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            manufacturers = Manufacturer.objects.all()

        # Pre-flight plugin check to make tests that patch get_manufacturer_plugin
        # surface errors uniformly.
        try:
            get_manufacturer_plugin("shure")  # This should be dynamic based on manufacturer
        except Exception as e:
            logger.exception("Plugin preflight failed: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Emit a signal to perform refresh logic in signal handlers.
        try:
            responses = refresh_requested.send_robust(
                sender=self.__class__, manufacturer=manufacturer_code, request=request
            )
            for _, resp in responses:
                if isinstance(resp, dict):
                    for code, details in resp.items():
                        refresh_results[code] = details
                        total_devices += details.get("device_count", details.get("count", 0))
                else:
                    refresh_results[str(_)] = {"error": str(resp)}
        except Exception as e:
            logger.exception("Error dispatching refresh_requested signal: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Also perform refresh directly in view for backward compatibility
        # This section should ideally be removed once signals are fully integrated
        try:
            for manufacturer in manufacturers:
                try:
                    plugin_class = get_manufacturer_plugin(manufacturer.code)
                    plugin = plugin_class(manufacturer)

                    devices_data = plugin.get_devices() or []
                    refresh_results[manufacturer.name] = {
                        "status": "success",
                        "device_count": len(devices_data),
                    }
                    total_devices += len(devices_data)
                except Exception as e:
                    logger.exception(f"Error refreshing data from {manufacturer.name}: {e}")
                    refresh_results[manufacturer.name] = {"status": "error", "error": str(e)}
        except Exception as e:
            logger.exception(f"Error refreshing data: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Clear cache to force fresh data (clear all manufacturer-specific caches)
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern("micboard_device_data_*")
        else:
            cache.clear()

        return Response(
            {
                "success": True,
                "message": "Data refresh triggered for manufacturers.",
                "manufacturers": refresh_results,
                "total_devices": total_devices,
                "timestamp": str(timezone.now()),
            }
        )


class UserAssignmentViewSet(viewsets.ModelViewSet):
    queryset = DeviceAssignment.objects.all()
    serializer_class = DeviceAssignmentSerializer
