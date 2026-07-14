"""Bounded synchronous HTTP transport for untrusted vendor responses."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any, NoReturn

import httpx

from micboard.services.common.network_limits import HTTP_RESPONSE_READ_CHUNK_BYTES, HTTPClientLimits
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class BoundedHTTPTransport:
    """Stream decoded response bytes through one strict size-enforcement seam."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        limits: HTTPClientLimits,
        oversized_response: Callable[[str], NoReturn],
    ) -> None:
        """Bind the current client, byte ceiling, and domain-specific failure callback."""
        self._client = client
        self._limits = limits
        self._oversized_response = oversized_response

    def send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Return a decoded successful response without reading beyond the byte ceiling."""
        with self._client.stream(method, url, **kwargs) as response:
            if response.status_code >= 400:
                return response

            self._enforce_declared_length(response, method=method)
            chunks: list[bytes] = []
            bytes_read = 0
            for chunk in response.iter_bytes(chunk_size=HTTP_RESPONSE_READ_CHUNK_BYTES):
                bytes_read += len(chunk)
                self._enforce_size(bytes_read, method=method)
                chunks.append(chunk)

            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=response.request,
                extensions=response.extensions,
            )

    def response_content(self, response: httpx.Response, *, method: str) -> bytes:
        """Enforce the same ceiling for an already-buffered successful response."""
        self._enforce_declared_length(response, method=method)
        content = response.content
        self._enforce_size(len(content), method=method)
        return content

    def extract_retry_after(self, response: httpx.Response) -> int | None:
        """Parse a positive Retry-After delay under the configured sleep ceiling."""
        try:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is None:
                return None
            retry_after = int(retry_after_header)
        except ValueError as exc:
            logger.exception(
                "Invalid Retry-After header in API response; value redacted",
                exc_info=sanitized_exception_info(exc),
            )
            return None
        if retry_after <= 0:
            return None
        return min(retry_after, math.ceil(self._limits.max_retry_delay_seconds))

    def _enforce_declared_length(self, response: httpx.Response, *, method: str) -> None:
        """Reject a valid Content-Length that exceeds the configured ceiling."""
        content_length = response.headers.get("Content-Length")
        if content_length is None:
            return
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = 0
        self._enforce_size(declared_length, method=method)

    def _enforce_size(self, size: int, *, method: str) -> None:
        """Delegate oversized failures to the owning API client's typed error path."""
        if size > self._limits.max_response_bytes:
            self._oversized_response(method)
