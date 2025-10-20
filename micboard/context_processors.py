"""
Context processors for micboard templates.
"""

from django.core.cache import cache

from micboard.models import Manufacturer


def api_health(request):
    """
    Context processor that provides API health status for all manufacturers.

    Returns a dict with:
    - api_health_status: Overall status ('healthy', 'unhealthy', 'partial', 'unconfigured')
    - api_health_details: List of dicts with manufacturer health info
    """
    cache_key = "api_health_status"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        return {"api_health": cached_result}

    manufacturers = Manufacturer.objects.filter(is_active=True)
    health_details = []
    healthy_count = 0
    total_count = 0

    for manufacturer in manufacturers:
        total_count += 1
        try:
            plugin_class = manufacturer.get_plugin_class()
            plugin = plugin_class(manufacturer)
            health_info = plugin.check_health()
            health_details.append(
                {
                    "manufacturer": manufacturer.name,
                    "code": manufacturer.code,
                    "status": health_info.get("status", "unknown"),
                    "details": health_info,
                }
            )
            if health_info.get("status") == "healthy":
                healthy_count += 1
        except Exception as e:
            health_details.append(
                {
                    "manufacturer": manufacturer.name,
                    "code": manufacturer.code,
                    "status": "error",
                    "details": {"error": str(e)},
                }
            )

    # Determine overall status
    if total_count == 0:
        overall_status = "unconfigured"
    elif healthy_count == total_count:
        overall_status = "healthy"
    elif healthy_count == 0:
        overall_status = "unhealthy"
    else:
        overall_status = "partial"

    result = {
        "status": overall_status,
        "details": health_details,
        "total_manufacturers": total_count,
        "healthy_manufacturers": healthy_count,
    }

    # Cache for 30 seconds
    cache.set(cache_key, result, timeout=30)

    return {"api_health": result}
