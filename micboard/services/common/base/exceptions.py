from __future__ import annotations

from contextlib import suppress

import httpx


class APIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: httpx.Response | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        if self.status_code:
            return f"{self.__class__.__name__}: {self.message} (Status: {self.status_code})"
        return f"{self.__class__.__name__}: {self.message}"


class APIRateLimitError(APIError):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        response: httpx.Response | None = None,
    ):
        super().__init__(message, status_code=429, response=response)
        self.retry_after = retry_after
        if response and "Retry-After" in response.headers:
            with suppress(ValueError, TypeError):
                self.retry_after = int(response.headers["Retry-After"])

    def __str__(self) -> str:
        if self.retry_after:
            return f"{self.__class__.__name__}: {self.message}. Retry after {self.retry_after} seconds."
        return f"{self.__class__.__name__}: {self.message}"
