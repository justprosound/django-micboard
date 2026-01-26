"""Common integration utilities shared across all manufacturer implementations.

This module provides shared base classes and utilities for:
- Rate limiting (decorators and context managers)
- Exception handling (base exception hierarchy)
- HTTP client helpers
- Data transformation utilities
- IP validation and hostname validation
"""

from .exceptions import APIError, APIRateLimitError
from .rate_limiter import rate_limit
from .utils import validate_hostname, validate_ipv4_address, validate_ipv4_list

__all__ = [
    "APIError",
    "APIRateLimitError",
    "rate_limit",
    "validate_hostname",
    "validate_ipv4_address",
    "validate_ipv4_list",
]
