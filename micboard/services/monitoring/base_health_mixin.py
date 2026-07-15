"""Health check mixin and utilities for django-micboard.

Centralizes health checking logic and standardizes responses across manufacturers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class HealthCheckMixin:
    """Mixin providing centralized health checking patterns.

    Use this mixin in services/clients that need to:
    1. Check API health in a standardized way
    2. Format health responses consistently
    3. Aggregate health from multiple sources
    4. Track health changes over time
    """

    def check_health(self) -> dict[str, Any]:
        """Check health for this resource.

        Implementations should call _standardize_health_response() on
        their raw health check result.

        Returns:
            Standardized health response
        """
        raise NotImplementedError("Subclasses must implement check_health()")

    def _standardize_health_response(
        self,
        *,
        status: str,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Standardize a health response to consistent format.

        All health responses follow this format:
        {
            "status": "healthy" | "degraded" | "unhealthy" | "error",
            "timestamp": ISO string,
            "details": {...}  # Manufacturer-specific details
        }

        Args:
            status: Health status (healthy, degraded, unhealthy, error)
            details: Optional details dictionary
            error: Optional error message if status is "error"

        Returns:
            Standardized health response
        """
        if status not in ("healthy", "degraded", "unhealthy", "error", "unknown"):
            logger.warning("Invalid health status: %s, defaulting to unknown", status)
            status = "unknown"

        response: dict[str, Any] = {
            "status": status,
            "timestamp": timezone.now().isoformat(),
        }

        if details:
            response["details"] = details
        if error:
            response["error"] = error

        return response

    def _parse_health_response(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        """Parse raw health response from API client into standardized format.

        Handles variations in health response formats from different
        manufacturers and API versions.

        Args:
            raw_response: Raw health response from API

        Returns:
            Standardized health response
        """
        if not raw_response:
            return self._standardize_health_response(status="error", error="Empty health response")

        # Try to extract status field (varies by manufacturer)
        status_field = raw_response.get("status")
        if not status_field:
            for field_name in ("healthy", "is_healthy", "api_healthy"):
                if field_name in raw_response:
                    status_field = raw_response[field_name]
                    break

        # Convert boolean to status string
        if isinstance(status_field, bool):
            status = "healthy" if status_field else "unhealthy"
        elif isinstance(status_field, str):
            # Normalize status value
            status_lower = status_field.lower()
            if status_lower in ("healthy", "ok", "up"):
                status = "healthy"
            elif status_lower in ("degraded", "partial"):
                status = "degraded"
            elif status_lower in ("unhealthy", "down"):
                status = "unhealthy"
            else:
                status = "unknown"
        else:
            status = "unknown"

        # Extract error if present
        error = (
            raw_response.get("error")
            or raw_response.get("error_message")
            or raw_response.get("message")
        )

        # Build details dict (exclude known status fields)
        status_fields = {"status", "healthy", "is_healthy", "api_healthy", "error", "error_message"}
        details = {k: v for k, v in raw_response.items() if k not in status_fields}

        return self._standardize_health_response(
            status=status,
            details=details or None,
            error=error,
        )

    def is_healthy(self) -> bool:
        """Check if this resource is currently healthy.

        Convenience method that returns boolean based on current health status.

        Returns:
            True if status is "healthy", False otherwise
        """
        health = self.check_health()
        return health.get("status") == "healthy"
