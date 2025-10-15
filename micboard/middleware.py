"""
Security middleware for Django Micboard.

Provides additional security headers and protections beyond Django's defaults.
"""

from __future__ import annotations

import logging
from typing import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.

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


class RequestLoggingMiddleware:
    """
    Middleware to log security-relevant requests.

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
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()

        for pattern in suspicious_patterns:
            if pattern in request_path or pattern in user_agent:
                logger.warning(
                    "Suspicious request detected: %s %s (User-Agent: %s, IP: %s)",
                    request.method,
                    request.get_full_path(),
                    request.META.get("HTTP_USER_AGENT", "Unknown"),
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
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            # Take the first IP if there are multiple
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "Unknown")
