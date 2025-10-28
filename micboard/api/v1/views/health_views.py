import logging

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from micboard.api.utils import _get_manufacturer_code
from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import (
    Manufacturer,
    Receiver,
)

logger = logging.getLogger(__name__)


class HealthCheckAPIView(APIView):
    """
    API endpoint for detailed health checks of the service and its dependencies.
    Combines logic from micboard.api.core_views.api_health and micboard.api.health_views.HealthCheckView.
    """

    def get(self, request, *args, **kwargs):
        health_status = {
            "status": "healthy",
            "timestamp": timezone.now().isoformat(),
            "version": "25.10.15",  # TODO: Get from app config
            "checks": {},
        }

        # Database check
        try:
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

        # Manufacturer API checks
        manufacturer_code = _get_manufacturer_code(request)
        try:
            manufacturers = Manufacturer.objects.all()
            manufacturer_checks = {}
            all_manufacturers_healthy = True

            for manufacturer in manufacturers:
                try:
                    plugin_class = get_manufacturer_plugin(manufacturer.code)
                    plugin = plugin_class(manufacturer)
                    client = plugin.get_client()
                    plugin_health = client.check_health()
                    manufacturer_checks[manufacturer.code] = plugin_health

                    if plugin_health.get("status") != "healthy":
                        all_manufacturers_healthy = False
                except Exception as e:
                    manufacturer_checks[manufacturer.code] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    all_manufacturers_healthy = False

            health_status["checks"]["manufacturers"] = manufacturer_checks
            if not all_manufacturers_healthy:
                health_status["status"] = "degraded"

        except Exception as e:
            health_status["checks"]["manufacturers"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"

        # Add receiver counts (from core_views.api_health)
        db_receivers_qs = Receiver.objects.all()
        if manufacturer_code:
            db_receivers_qs = db_receivers_qs.filter(manufacturer__code=manufacturer_code)

        health_status["checks"]["database"]["receivers_total"] = db_receivers_qs.count()
        health_status["checks"]["database"]["receivers_active"] = db_receivers_qs.filter(
            is_active=True
        ).count()
        # Assuming 'healthy' means 'active' for now, adjust if model has a specific 'healthy' field
        health_status["checks"]["database"]["receivers_healthy"] = db_receivers_qs.filter(
            is_active=True
        ).count()

        status_code = 200 if health_status["status"] == "healthy" else 503
        return Response(health_status, status=status_code)


class ReadinessCheckAPIView(APIView):
    """
    Readiness check endpoint for Kubernetes/load balancer health checks.
    """

    def get(self, request, *args, **kwargs):
        try:
            # Quick database check
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            return Response(
                {
                    "status": "ready",
                    "timestamp": timezone.now().isoformat(),
                    "api_version": "1.0.0",  # TODO: Get from base_views or app config
                }
            )
        except Exception as e:
            logger.exception("Readiness check failed")
            return Response(
                {
                    "status": "not ready",
                    "error": str(e),
                    "timestamp": timezone.now().isoformat(),
                    "api_version": "1.0.0",  # TODO: Get from base_views or app config
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
