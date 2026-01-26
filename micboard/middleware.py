"""Custom middleware for django-micboard.

Provides request logging, performance monitoring, connection health tracking, and security.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from micboard.services import ConnectionHealthService

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """Log all requests with timing information."""

    def process_request(self, request: HttpRequest) -> None:
        """Store request start time."""
        request._start_time = time.time()  # type: ignore[attr-defined]

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Log request with timing."""
        if hasattr(request, "_start_time"):
            duration = time.time() - request._start_time
            logger.info(
                f"{request.method} {request.path} - {response.status_code} "
                f"({duration * 1000:.2f}ms)"
            )
        return response


class ConnectionHealthMiddleware(MiddlewareMixin):
    """Track connection health for manufacturer APIs."""

    def process_request(self, request: HttpRequest) -> None:
        """Check connection health on each request."""
        # Only check for API endpoints
        if request.path.startswith("/api/"):
            try:
                unhealthy = ConnectionHealthService.get_unhealthy_connections(
                    heartbeat_timeout_seconds=60
                )

                if unhealthy:
                    logger.warning(
                        f"Unhealthy connections detected: "
                        f"{[c['manufacturer_code'] for c in unhealthy]}"
                    )

                    # Store in request for use in views
                    request.unhealthy_connections = unhealthy  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"Error checking connection health: {e}")


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """Monitor slow requests and log performance warnings."""

    SLOW_REQUEST_THRESHOLD = 1.0  # seconds

    def process_request(self, request: HttpRequest) -> None:
        """Store request start time."""
        request._perf_start_time = time.time()  # type: ignore[attr-defined]

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Check for slow requests."""
        if hasattr(request, "_perf_start_time"):
            duration = time.time() - request._perf_start_time

            if duration > self.SLOW_REQUEST_THRESHOLD:
                logger.warning(
                    f"SLOW REQUEST: {request.method} {request.path} took {duration:.2f}s"
                )

                # Add custom header for monitoring
                response["X-Response-Time"] = f"{duration:.3f}"

        return response


class APIVersionMiddleware(MiddlewareMixin):
    """Add API version information to responses."""

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add version header to API responses."""
        if request.path.startswith("/api/"):
            # Import here to avoid circular imports
            from micboard import __version__

            response["X-API-Version"] = __version__

        return response


class SecurityHeadersMiddleware:
    """Middleware to add security headers to all responses.

    Adds headers for:
    - Content Security Policy (CSP)
    - X-Frame-Options
    - X-Content-Type-Options
    - Referrer-Policy
    - Permissions-Policy
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Allow Django admin scripts
            "style-src 'self' 'unsafe-inline'; "  # Allow Django admin styles
            "img-src 'self' data: https:; "  # Allow data URLs and HTTPS images
            "font-src 'self'; "
            "connect-src 'self' ws: wss:; "  # Allow WebSocket connections
            "frame-ancestors 'none';"  # Prevent clickjacking
        )
        response["Content-Security-Policy"] = csp

        # Prevent clickjacking
        response["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response["X-Content-Type-Options"] = "nosniff"

        # Referrer policy
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (restrict features)
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )

        # Remove server header for security
        response.headers.pop("Server", None)

        return response


class SecurityLoggingMiddleware:
    """Middleware to log security-relevant requests.

    Logs suspicious requests that might indicate security issues.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Log potentially suspicious requests
        suspicious_patterns = [
            "../../",  # Path traversal attempts
            "<script",  # XSS attempts
            "union select",  # SQL injection attempts
            "eval(",  # Code injection attempts
        ]

        request_path = request.get_full_path().lower()
        user_agent = request.headers.get("user-agent", "").lower()

        for pattern in suspicious_patterns:
            if pattern in request_path or pattern in user_agent:
                logger.warning(
                    "Suspicious request detected: %s %s (User-Agent: %s, IP: %s)",
                    request.method,
                    request.get_full_path(),
                    request.headers.get("user-agent", "Unknown"),
                    self._get_client_ip(request),
                )
                break

        response = self.get_response(request)

        # Log authentication failures
        if response.status_code == 401:
            logger.info(
                "Authentication failure: %s %s (IP: %s)",
                request.method,
                request.get_full_path(),
                self._get_client_ip(request),
            )

        return response

    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get the client IP address from the request."""
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            # Take the first IP if there are multiple
            return str(x_forwarded_for).split(",")[0].strip()
        return str(request.META.get("REMOTE_ADDR", "Unknown"))
