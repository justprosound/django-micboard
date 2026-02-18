from micboard.services.shared.api_health import get_api_health


def api_health(request):
    """Context processor that provides API health status for all manufacturers (delegates to service)."""
    return {"api_health": get_api_health()}
