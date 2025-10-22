"""Base API view utilities for micboard.

This module provides lightweight base view helpers used by the v1 API
views and is intentionally small. Tests require a module docstring for
quality checks.
"""

import logging

from django.http import HttpRequest
from django.views import View

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
