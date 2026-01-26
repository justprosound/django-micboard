"""Shure System API exception classes.

This module provides Shure-specific exceptions that inherit from
the common exception hierarchy while maintaining their distinct identities.
"""

from __future__ import annotations

# Import base exceptions
from micboard.integrations.common.exceptions import APIError, APIRateLimitError


class ShureAPIError(APIError):
    """Shure System API error exception."""

    pass


class ShureAPIRateLimitError(ShureAPIError, APIRateLimitError):
    """Shure System API rate limit error exception."""

    pass


__all__ = ["ShureAPIError", "ShureAPIRateLimitError"]
