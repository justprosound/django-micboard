"""
Exceptions for Sennheiser SSCv2 API.
"""

from __future__ import annotations


class SennheiserAPIError(Exception):
    """Base exception for Sennheiser API errors."""

    def __init__(self, message: str, status_code: int | None = None, response=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response


class SennheiserAPIRateLimitError(SennheiserAPIError):
    """Exception for rate limit errors."""

    def __init__(self, message: str, retry_after: int | None = None, response=None):
        super().__init__(message, status_code=429, response=response)
        self.retry_after = retry_after
