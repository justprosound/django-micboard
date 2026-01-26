"""Health check mixin and utilities for django-micboard.

Centralizes health checking logic and standardizes responses across manufacturers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from django.utils import timezone

if TYPE_CHECKING:
    pass

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

        response = {
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
            # Try alternative names
            status_field = (
                raw_response.get("healthy")
                or raw_response.get("is_healthy")
                or raw_response.get("api_healthy")
            )

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

    def is_degraded(self) -> bool:
        """Check if this resource is currently degraded.

        Returns:
            True if status is "degraded"
        """
        health = self.check_health()
        return health.get("status") == "degraded"

    def is_unhealthy(self) -> bool:
        """Check if this resource is currently unhealthy or in error.

        Returns:
            True if status is "unhealthy" or "error"
        """
        health = self.check_health()
        return health.get("status") in ("unhealthy", "error")


class AggregatedHealthChecker:
    """Aggregates health status from multiple sources.

    Useful for computing overall system health from individual
    manufacturers, API clients, databases, etc.
    """

    def __init__(self):
        """Initialize health aggregator."""
        self.checks: dict[str, HealthCheckMixin] = {}

    def add_check(self, name: str, checker: HealthCheckMixin) -> None:
        """Add a health check source.

        Args:
            name: Identifier for this check
            checker: Object with check_health() method
        """
        self.checks[name] = checker

    def get_overall_health(self) -> dict[str, Any]:
        """Get aggregated health status.

        Returns:
            {
                "overall_status": "healthy" | "degraded" | "unhealthy",
                "timestamp": ISO string,
                "details": {
                    "check_name": {...}
                }
            }
        """
        if not self.checks:
            return {
                "overall_status": "unknown",
                "timestamp": timezone.now().isoformat(),
                "details": {},
            }

        results = {}
        worst_status = "healthy"

        for name, checker in self.checks.items():
            try:
                result = checker.check_health()
                results[name] = result

                # Track worst status
                status = result.get("status", "unknown")
                if status == "error":
                    worst_status = "error"
                elif status == "unhealthy" and worst_status != "error":
                    worst_status = "unhealthy"
                elif status == "degraded" and worst_status not in ("error", "unhealthy"):
                    worst_status = "degraded"

            except Exception as e:
                error_msg = f"Health check failed: {e}"
                logger.exception("Error checking health for %s", name)
                results[name] = {
                    "status": "error",
                    "timestamp": timezone.now().isoformat(),
                    "error": error_msg,
                }
                worst_status = "error"

        return {
            "overall_status": worst_status,
            "timestamp": timezone.now().isoformat(),
            "details": results,
        }

    def get_healthy_checks(self) -> list[str]:
        """Get names of all healthy checks."""
        health = self.get_overall_health()
        return [
            name
            for name, result in health.get("details", {}).items()
            if result.get("status") == "healthy"
        ]

    def get_unhealthy_checks(self) -> list[str]:
        """Get names of all unhealthy/error checks."""
        health = self.get_overall_health()
        return [
            name
            for name, result in health.get("details", {}).items()
            if result.get("status") in ("unhealthy", "error")
        ]


def create_health_check_reporter(
    *,
    log_to_db: bool = False,
    send_alerts: bool = False,
) -> Callable:
    """Create a health check reporter that logs/alerts on status changes.

    Args:
        log_to_db: If True, log health checks to database
        send_alerts: If True, send alerts on unhealthy status

    Returns:
        Reporter function(name, health_status)
    """

    def reporter(name: str, health_status: dict[str, Any]) -> None:
        """Report health status."""
        status = health_status.get("status", "unknown")
        logger.info("Health check %s: %s", name, status)

        if log_to_db:
            try:
                from micboard.models import HealthCheckLog

                HealthCheckLog.objects.create(
                    check_name=name,
                    status=status,
                    details=health_status.get("details"),
                )
            except Exception:
                logger.exception("Failed to log health check to database")

        if send_alerts and status in ("unhealthy", "error"):
            try:
                from micboard.services.alerts import create_health_alert

                create_health_alert(
                    name,
                    status,
                    health_status.get("error"),
                )
            except Exception:
                logger.exception("Failed to send health alert")

    return reporter
