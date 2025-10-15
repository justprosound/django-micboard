"""
Shure System API client package.

This package provides tools for interacting with the Shure System API:
- HTTP client with connection pooling and retry logic
- Data transformers for converting API format to micboard format
- WebSocket support for real-time device updates
"""

from __future__ import annotations

from .client import (
    ShureAPIError,
    ShureAPIRateLimitError,
    ShureSystemAPIClient,
    rate_limit,
)
from .transformers import ShureDataTransformer
from .websocket import ShureWebSocketError, connect_and_subscribe

__all__ = [
    "ShureAPIError",
    "ShureAPIRateLimitError",
    "ShureDataTransformer",
    "ShureSystemAPIClient",
    "ShureWebSocketError",
    "connect_and_subscribe",
    "rate_limit",
]
