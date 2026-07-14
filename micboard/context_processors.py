from typing import Any

from django.http import HttpRequest

from micboard.services.shared.api_health import get_api_health


def api_health(request: HttpRequest) -> dict[str, Any]:
    """Expose the latest bounded health snapshots without request-time API probes."""
    return {"api_health": get_api_health()}
