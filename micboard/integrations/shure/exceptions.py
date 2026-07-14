"""Exceptions shared by Shure integration clients."""

from micboard.services.common.base.exceptions import APIError, APIRateLimitError


class ShureAPIError(APIError):
    """Shure System API request failed."""


class ShureAPIRateLimitError(ShureAPIError, APIRateLimitError):
    """Shure System API rate limit was exceeded."""
