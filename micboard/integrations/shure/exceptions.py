"""Shure-specific exceptions at the manufacturer integration boundary."""

from micboard.exceptions import APIError, APIRateLimitError


class ShureAPIError(APIError):
    """Shure System API request failed."""


class ShureAPIRateLimitError(ShureAPIError, APIRateLimitError):
    """Shure System API rate limit was exceeded."""
