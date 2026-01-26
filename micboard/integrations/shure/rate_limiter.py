"""Rate limiting for Shure System API client.

This module re-exports the common rate limiter for backward compatibility.
For new code, import directly from micboard.integrations.common.
"""

from __future__ import annotations

# Re-export from common for backward compatibility
from micboard.integrations.common.rate_limiter import rate_limit

__all__ = ["rate_limit"]
