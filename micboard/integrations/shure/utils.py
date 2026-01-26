"""Utility functions for Shure System API integration.

This module re-exports common utilities for backward compatibility.
For new code, import directly from micboard.integrations.common.utils.
"""

from __future__ import annotations

# Re-export from common for backward compatibility
from micboard.integrations.common.utils import (
    validate_hostname,
    validate_ipv4_address,
    validate_ipv4_list,
)

__all__ = ["validate_hostname", "validate_ipv4_address", "validate_ipv4_list"]
