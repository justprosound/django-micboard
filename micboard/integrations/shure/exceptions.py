from __future__ import annotations

import requests


class ShureAPIError(Exception):
    """Base exception for Shure System API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: requests.Response | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self):
        if self.status_code:
            return f"ShureAPIError: {self.message} (Status: {self.status_code})"
        return f"ShureAPIError: {self.message}"


class ShureAPIRateLimitError(ShureAPIError):
    """Exception for Shure System API rate limit errors (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        response: requests.Response | None = None,
    ):
        super().__init__(message, status_code=429, response=response)
        self.retry_after = retry_after
        if response and "Retry-After" in response.headers:
            try:
                self.retry_after = int(response.headers["Retry-After"])
            except ValueError:
                pass

    def __str__(self):
        if self.retry_after:
            return (
                f"ShureAPIRateLimitError: {self.message}. Retry after {self.retry_after} seconds."
            )
        return f"ShureAPIRateLimitError: {self.message}"
