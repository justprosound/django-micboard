"""Base exception classes for manufacturer API integrations.

Provides a common exception hierarchy that all manufacturer integrations
can inherit from, ensuring consistent error handling across the codebase.
"""

from __future__ import annotations

import requests


class APIError(Exception):
    """Base exception for API errors across all manufacturer integrations."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: requests.Response | None = None,
    ):
        """Initialize API error.

        Args:
            message: Human-readable error message
            status_code: HTTP status code from the API response
            response: The requests.Response object (if available)
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        """Return formatted error string."""
        if self.status_code:
            return f"{self.__class__.__name__}: {self.message} (Status: {self.status_code})"
        return f"{self.__class__.__name__}: {self.message}"


class APIRateLimitError(APIError):
    """Exception for API rate limit errors (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        response: requests.Response | None = None,
    ):
        """Initialize rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Seconds to wait before retrying (from Retry-After header)
            response: The requests.Response object
        """
        super().__init__(message, status_code=429, response=response)
        self.retry_after = retry_after
        if response and "Retry-After" in response.headers:
            try:
                self.retry_after = int(response.headers["Retry-After"])
            except (ValueError, TypeError):
                pass

    def __str__(self) -> str:
        """Return formatted error string with retry information."""
        if self.retry_after:
            return (
                f"{self.__class__.__name__}: {self.message}. "
                f"Retry after {self.retry_after} seconds."
            )
        return f"{self.__class__.__name__}: {self.message}"
