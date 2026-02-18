"""Logging mode controller for dynamic verbosity management.

Manages verbosity state:
  - passive: Critical logs only
  - normal: Standard operational logging (default)
  - high: Fine-grained debugging/trace logging

Supports automatic expiry (TTL) to prevent accidental high-churn modes.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from django.core.cache import cache

logger = logging.getLogger(__name__)

LogMode = Literal["passive", "normal", "high"]
CACHE_KEY = "micboard_logging_mode"
CACHE_EXPIRY_KEY = "micboard_logging_mode_expiry"


class LoggingModeService:
    """Business logic for dynamic logging levels."""

    @staticmethod
    def get_current_mode() -> LogMode:
        """Get the currently active logging mode."""
        mode = cache.get(CACHE_KEY, "normal")
        expiry = cache.get(CACHE_EXPIRY_KEY)

        if expiry and time.time() > expiry:
            # Mode has expired, reset to normal
            LoggingModeService.set_mode("normal")
            return "normal"

        return mode

    @staticmethod
    def set_mode(mode: LogMode, ttl_seconds: int | None = None) -> None:
        """Set the active logging mode with optional TTL."""
        cache.set(CACHE_KEY, mode, timeout=None)

        if ttl_seconds:
            expiry = time.time() + ttl_seconds
            cache.set(CACHE_EXPIRY_KEY, expiry, timeout=None)
            logger.info(f"Logging mode set to '{mode}' for {ttl_seconds}s")
        else:
            cache.delete(CACHE_EXPIRY_KEY)
            logger.info(f"Logging mode set to '{mode}' (no expiry)")

    @staticmethod
    def should_log(level: LogMode) -> bool:
        """Check if an event should be logged based on current mode."""
        current = LoggingModeService.get_current_mode()

        # Priority mapping
        priority = {"passive": 0, "normal": 1, "high": 2}
        return priority.get(level, 1) <= priority.get(current, 1)
