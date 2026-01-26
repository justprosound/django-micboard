"""Sennheiser SSCv2 API exception classes.

This module provides Sennheiser-specific exceptions that inherit from
the common exception hierarchy while maintaining their distinct identities.
"""

from __future__ import annotations

# Import base exceptions
from micboard.integrations.common.exceptions import APIError, APIRateLimitError


class SennheiserAPIError(APIError):
    """Sennheiser API error exception."""

    pass


class SennheiserAPIRateLimitError(SennheiserAPIError, APIRateLimitError):
    """Sennheiser API rate limit error exception."""

    pass


__all__ = ["SennheiserAPIError", "SennheiserAPIRateLimitError"]
