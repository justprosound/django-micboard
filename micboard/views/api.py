"""
API views for the micboard app.
"""

import json
import logging
from typing import Any

from django.core.cache import cache
from django.db import models
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt

from micboard.decorators import rate_limit_view
from micboard.manufacturers import get_manufacturer_plugin

# Updated imports
from micboard.models import DiscoveredDevice, Group, Manufacturer, MicboardConfig, Receiver
from micboard.serializers import (
    serialize_discovered_device,
    serialize_group,
    serialize_receiver_detail,
    serialize_receiver_summary,
    serialize_receivers,
)
from micboard.signals import discover_requested, refresh_requested

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
                return str(version_part).strip()
            except (IndexError, ValueError):
                pass

        # Check query parameter
        version = request.GET.get("version")
        if version:
            return str(version)

        # Default to current version
        return self.API_VERSION


@rate_limit_view(max_requests=120, window_seconds=60)  # 2 requests per second
@cache_page(30)  # Cache for 30 seconds
def data_json(request):
    """API endpoint for device data, similar to micboard_json"""
    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        # Try to get fresh data from cache first (with manufacturer-specific cache key)
        cache_key = f"micboard_device_data_{manufacturer_code or 'all'}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return JsonResponse(cached_data)

        # Use serializer for consistent data structure
        receivers_data = serialize_receivers(
            include_extra=True, manufacturer_code=manufacturer_code
        )

        # Serialize discovered devices (filter by manufacturer if specified)
        discovered_query = DiscoveredDevice.objects.all()
        if manufacturer_code:
            # Filter discovered devices by manufacturer if we can determine it
            # This might need refinement based on how discovered devices are associated with manufacturers
            discovered_query = discovered_query.filter()  # Placeholder for future filtering logic

        discovered = [serialize_discovered_device(disc) for disc in discovered_query]

        # Serialize config
        config_query = MicboardConfig.objects.all()

        # Filter config by manufacturer if specified
        if manufacturer_code:
            # Include both global configs (manufacturer=null) and manufacturer-specific configs
            config_query = config_query.filter(
                models.Q(manufacturer__code=manufacturer_code) | models.Q(manufacturer__isnull=True)
            )
        else:
            # For all manufacturers, include only global configs
            config_query = config_query.filter(manufacturer__isnull=True)

        config = {conf.key: conf.value for conf in config_query}

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

    def get(self, request):
        """Get configuration values"""
        try:
            manufacturer_code = request.GET.get("manufacturer")

            config_query = MicboardConfig.objects.all()

            # Filter config by manufacturer if specified
            if manufacturer_code:
                try:
                    manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                    # Include both global configs and manufacturer-specific configs
                    config_query = config_query.filter(
                        models.Q(manufacturer=manufacturer) | models.Q(manufacturer__isnull=True)
                    )
                except Manufacturer.DoesNotExist:
                    return JsonResponse(
                        {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                    )
            else:
                # For all manufacturers, include only global configs
                config_query = config_query.filter(manufacturer__isnull=True)

            config = {conf.key: conf.value for conf in config_query}
            return JsonResponse({"config": config})
        except Exception as e:
            logger.exception(f"Config retrieval error: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    def post(self, request):
        try:
            data = json.loads(request.body)
            manufacturer_code = request.GET.get("manufacturer")

            # Get or create manufacturer if specified
            manufacturer = None
            if manufacturer_code:
                try:
                    manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                except Manufacturer.DoesNotExist:
                    return JsonResponse(
                        {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                    )

            # Update or create configs
            for key, value in data.items():
                MicboardConfig.objects.update_or_create(
                    key=key, manufacturer=manufacturer, defaults={"value": str(value)}
                )

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
    """Trigger device discovery via manufacturer APIs"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        total_discovered = 0
        all_devices: list[dict[str, Any]] = []
        manufacturer_results = {}

        # Get manufacturers to discover from (not used here; handlers manage selection)
        if manufacturer_code:
            try:
                _ = Manufacturer.objects.get(code=manufacturer_code)
                # selection validated; handlers will perform the discovery
            except Manufacturer.DoesNotExist:
                return JsonResponse(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                )
        else:
            # Not used in view because discovery is performed in signal handlers
            pass

        # Emit a signal to perform discovery logic in signal handlers.
        # Handlers will return a dict mapping manufacturer code -> result.
        try:
            responses = discover_requested.send_robust(
                api_discover, manufacturer=manufacturer_code, request=request
            )
            # responses is list of (receiver, result)
            for _, resp in responses:
                if isinstance(resp, dict):
                    for code, details in resp.items():
                        manufacturer_results[code] = details
                        total_discovered += details.get("count", details.get("device_count", 0))
                else:
                    # Handler returned non-dict (usually error message)
                    manufacturer_results[str(_)] = {"error": str(resp)}
        except Exception as e:
            logger.exception("Error dispatching discover_requested signal: %s", e)
            return JsonResponse({"error": str(e)}, status=500)

        return JsonResponse(
            {
                "success": True,
                "total_discovered": total_discovered,
                "manufacturers": manufacturer_results,
                "devices": all_devices,
            }
        )
    except Exception as e:
        logger.exception(f"Error discovering devices: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@rate_limit_view(max_requests=10, window_seconds=60)  # Limit refresh requests
def api_refresh(request):
    """Force refresh device data from manufacturer APIs"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        refresh_results = {}
        total_devices = 0

        # Get manufacturers to refresh from (handlers manage selection)
        if manufacturer_code:
            try:
                _ = Manufacturer.objects.get(code=manufacturer_code)
                # selection validated; handlers will perform the refresh
            except Manufacturer.DoesNotExist:
                return JsonResponse(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                )
        else:
            # Not used in view because refresh is performed in signal handlers
            pass

        # Emit a signal to perform refresh logic in signal handlers.
        try:
            responses = refresh_requested.send_robust(
                api_refresh, manufacturer=manufacturer_code, request=request
            )
            for _, resp in responses:
                if isinstance(resp, dict):
                    for code, details in resp.items():
                        refresh_results[code] = details
                        total_devices += details.get("device_count", details.get("count", 0))
                else:
                    refresh_results[str(_)] = {"status": "error", "error": str(resp)}
        except Exception as e:
            logger.exception("Error dispatching refresh_requested signal: %s", e)
            return JsonResponse({"error": str(e)}, status=500)

        # Clear cache to force fresh data (clear all manufacturer-specific caches)
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern("micboard_device_data_*")
        else:
            cache.clear()

        return JsonResponse(
            {
                "success": True,
                "message": "Data refresh triggered for manufacturers.",
                "manufacturers": refresh_results,
                "total_devices": total_devices,
                "timestamp": str(timezone.now()),
            }
        )
    except Exception as e:
        logger.exception(f"Error refreshing data: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@rate_limit_view(max_requests=30, window_seconds=60)
def api_health(request):
    """Health check endpoint for the API and manufacturer connectivity"""
    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        health_info = {
            "api_status": "healthy",
            "timestamp": timezone.now().isoformat(),
            "database": {
                "receivers_total": Receiver.objects.count(),
                "receivers_active": Receiver.objects.active().count(),
                "receivers_healthy": Receiver.objects.filter(is_active=True).count(),
            },
            "manufacturers": {},
        }

        # Get manufacturers to check
        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                manufacturers = [manufacturer]
            except Manufacturer.DoesNotExist:
                return JsonResponse(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                )
        else:
            manufacturers = Manufacturer.objects.all()

        # Check each manufacturer's health
        for manufacturer in manufacturers:
            try:
                plugin_class = get_manufacturer_plugin(manufacturer.code)
                plugin = plugin_class(manufacturer)

                # Get health status from plugin
                plugin_health = plugin.check_health()
                health_info["manufacturers"][manufacturer.name] = plugin_health

                # If any manufacturer is unhealthy, mark overall API as degraded
                if plugin_health.get("status") != "healthy":
                    health_info["api_status"] = "degraded"

            except Exception as e:
                logger.warning(f"Manufacturer health check failed for {manufacturer.name}: {e}")
                health_info["manufacturers"][manufacturer.name] = {
                    "status": "unavailable",
                    "error": str(e),
                }
                health_info["api_status"] = "degraded"

        return JsonResponse(health_info)
    except Exception as e:
        logger.exception(f"Health check error: {e}")
        return JsonResponse({"error": "Health check failed", "detail": str(e)}, status=500)


@rate_limit_view(max_requests=60, window_seconds=60)
def api_receiver_detail(request, receiver_id):
    """Get detailed information for a specific receiver"""
    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        # Base queryset
        receiver_query = Receiver.objects.prefetch_related("channels__transmitter")

        # Filter by manufacturer if specified
        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                receiver_query = receiver_query.filter(manufacturer=manufacturer)
            except Manufacturer.DoesNotExist:
                return JsonResponse(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                )

        receiver = receiver_query.get(api_device_id=receiver_id)
        data = serialize_receiver_detail(receiver)
        return JsonResponse(data)
    except Receiver.DoesNotExist:
        return JsonResponse({"error": "Receiver not found"}, status=404)
    except Exception as e:
        logger.exception(f"Error fetching receiver detail: {e}")
        return JsonResponse({"error": "Internal server error", "detail": str(e)}, status=500)


@rate_limit_view(max_requests=30, window_seconds=60)
def api_device_detail(request, device_id):
    """On-demand fetch of a device's current data from the manufacturer API.

    Delegates to device_detail_requested signal to keep views thin.
    """
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    manufacturer_code = request.GET.get("manufacturer")
    try:
        from micboard.signals import device_detail_requested

        responses = device_detail_requested.send_robust(
            api_device_detail, manufacturer=manufacturer_code, device_id=device_id, request=request
        )
        for _, resp in responses:
            if isinstance(resp, dict):
                return JsonResponse({"success": True, "result": resp})
        return JsonResponse({"error": "No data found"}, status=404)
    except Exception as e:
        logger.exception("Error fetching device detail: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@rate_limit_view(max_requests=10, window_seconds=60)
def api_add_discovery_ips(request):
    """Add IP addresses to the manufacturer's discovery list (POST).

    Delegates to add_discovery_ips_requested signal.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ips = payload.get("ips")
    if not ips or not isinstance(ips, list):
        return JsonResponse({"error": "'ips' must be a list of IPv4 addresses"}, status=400)

    manufacturer_code = request.GET.get("manufacturer")
    try:
        from micboard.signals import add_discovery_ips_requested

        responses = add_discovery_ips_requested.send_robust(
            api_add_discovery_ips, manufacturer=manufacturer_code, ips=ips, request=request
        )
        results = {}
        for _, resp in responses:
            if isinstance(resp, dict):
                results.update(resp)
        return JsonResponse({"success": True, "results": results})
    except Exception as e:
        logger.exception("Error adding discovery ips: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@rate_limit_view(max_requests=60, window_seconds=60)
def api_receivers_list(request):
    """Get list of all receivers with basic information"""
    try:
        # Get manufacturer filter from query parameters
        manufacturer_code = request.GET.get("manufacturer")

        # Base queryset
        receivers_query = Receiver.objects.all().order_by("name")

        # Filter by manufacturer if specified
        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                receivers_query = receivers_query.filter(manufacturer=manufacturer)
            except Manufacturer.DoesNotExist:
                return JsonResponse(
                    {"error": f"Manufacturer '{manufacturer_code}' not found"}, status=404
                )

        receivers = [serialize_receiver_summary(receiver) for receiver in receivers_query]

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

            # Shure API check - now check all manufacturer plugins
        try:
            manufacturers = Manufacturer.objects.all()
            manufacturer_checks = {}

            for manufacturer in manufacturers:
                try:
                    plugin_class = get_manufacturer_plugin(manufacturer.code)
                    plugin = plugin_class(manufacturer)
                    health_status = plugin.check_health()
                    manufacturer_checks[manufacturer.code] = health_status

                    # If any manufacturer plugin is unhealthy, mark overall health as degraded
                    if health_status.get("status") != "healthy":
                        health_status["status"] = "degraded"
                except Exception as e:
                    manufacturer_checks[manufacturer.code] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    health_status["status"] = "degraded"

            health_status["checks"]["manufacturers"] = manufacturer_checks

        except Exception as e:
            health_status["checks"]["manufacturers"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"

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
                    "description": "Basic health check with manufacturer status",
                    "parameters": {"manufacturer": "Optional: Check specific manufacturer only"},
                    "response": {
                        "api_status": "healthy|degraded",
                        "timestamp": "ISO 8601 timestamp",
                        "database": {"receivers_total": 0, "receivers_active": 0},
                        "manufacturers": {"ManufacturerName": {"status": "healthy", "details": {}}},
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
                    "parameters": {
                        "manufacturer": "Optional: Filter by manufacturer code (e.g., 'shure')"
                    },
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
                    "parameters": {
                        "manufacturer": "Optional: Filter by manufacturer code (e.g., 'shure')"
                    },
                    "response": {"receivers": [], "count": 0},
                },
                "receiver_detail": {
                    "url": "/api/receivers/{id}/",
                    "method": "GET",
                    "description": "Detailed information for a specific receiver",
                    "parameters": {
                        "id": "Receiver ID",
                        "manufacturer": "Optional: Filter by manufacturer code (e.g., 'shure')",
                    },
                    "response": {"api_device_id": "string", "name": "string", "channels": []},
                },
                "discover": {
                    "url": "/api/discover/",
                    "method": "POST",
                    "description": "Trigger device discovery on the network",
                    "parameters": {
                        "manufacturer": "Optional: Discover from specific manufacturer only"
                    },
                    "response": {
                        "success": True,
                        "total_discovered": 0,
                        "manufacturers": {"ManufacturerName": {"count": 0, "devices": []}},
                        "devices": [],
                    },
                },
                "refresh": {
                    "url": "/api/refresh/",
                    "method": "POST",
                    "description": "Force refresh of device data from manufacturer APIs",
                    "parameters": {
                        "manufacturer": "Optional: Refresh from specific manufacturer only"
                    },
                    "response": {
                        "success": True,
                        "message": "Data refresh triggered",
                        "manufacturers": {
                            "ManufacturerName": {"status": "success", "device_count": 0}
                        },
                        "total_devices": 0,
                    },
                },
                "config": {
                    "url": "/api/config/",
                    "method": "GET|POST",
                    "description": "Get or update application configuration",
                    "parameters": {
                        "manufacturer": "Optional: Filter by manufacturer code for manufacturer-specific configs"
                    },
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
