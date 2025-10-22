"""Compatibility exports for older import paths used by tests.

This module re-exports views and helper functions from the newer
`micboard.api` package layout so tests and external code importing
`micboard.api.views` continue to work.
"""

from micboard.api.base_views import APIView, VersionedAPIView
from micboard.api.v1.views.config_views import ConfigAPIView as ConfigHandler
from micboard.api.v1.views.config_views import GroupUpdateAPIView as GroupUpdateHandler

# Convenience function exports used by tests and older codepaths
from micboard.api.v1.views.discovery_views import AddDiscoveryIPsAPIView
from micboard.api.v1.views.health_views import HealthCheckAPIView as HealthCheckView
from micboard.api.v1.views.health_views import ReadinessCheckAPIView as ReadinessCheckView

# Basic view functions and handlers live in the micboard package in various
# locations; import and re-export the commonly-used symbols expected by tests.
from micboard.api.v1.views.other_views import APIDocumentationAPIView as APIDocumentationView
from micboard.context_processors import api_health

# data_json and other helpers are provided elsewhere in the project; try to
# import them if present.
try:
    from micboard.views.api import (
        api_discover,
        api_receiver_detail,
        api_receivers_list,
        api_refresh,
        data_json,
    )
except Exception:  # pragma: no cover - best-effort import
    # Provide fallbacks so imports don't fail at test collection time.
    def api_discover(request):
        from django.http import HttpResponse

        return HttpResponse("Not implemented", status=501)

    def api_receiver_detail(request, receiver_id=None):
        from django.http import HttpResponse

        return HttpResponse("Not implemented", status=501)

    def api_receivers_list(request):
        from django.http import HttpResponse

        return HttpResponse("Not implemented", status=501)

    def api_refresh(request):
        from django.http import HttpResponse

        return HttpResponse("Not implemented", status=501)

    def data_json(request):
        from django.http import HttpResponse

        return HttpResponse("Not implemented", status=501)


__all__ = [
    "APIDocumentationView",
    "APIView",
    "AddDiscoveryIPsAPIView",
    "ConfigHandler",
    "GroupUpdateHandler",
    "HealthCheckView",
    "ReadinessCheckView",
    "VersionedAPIView",
    "api_discover",
    "api_health",
    "api_receiver_detail",
    "api_receivers_list",
    "api_refresh",
    "data_json",
]
