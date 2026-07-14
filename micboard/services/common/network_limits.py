"""Validated package ceilings for untrusted vendor network responses."""

from __future__ import annotations

import math

from django.conf import settings

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

DEFAULT_HTTP_MAX_RETRY_DELAY_SECONDS = 30.0
HARD_MAX_HTTP_RETRY_DELAY_SECONDS = 300.0
DEFAULT_HTTP_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HARD_MAX_HTTP_RESPONSE_BYTES = 16 * 1024 * 1024
HTTP_RESPONSE_READ_CHUNK_BYTES = 8 * 1024
DEFAULT_SSE_MAX_LINE_BYTES = 64 * 1024
HARD_MAX_SSE_LINE_BYTES = 1024 * 1024
DEFAULT_SSE_MAX_EVENT_BYTES = 64 * 1024
HARD_MAX_SSE_EVENT_BYTES = 1024 * 1024
SSE_READ_CHUNK_BYTES = 8 * 1024


class HTTPClientLimits(PydanticBaseDTO):
    """Host-configured HTTP limits constrained by package hard ceilings."""

    max_retry_delay_seconds: float = Field(gt=0, le=HARD_MAX_HTTP_RETRY_DELAY_SECONDS)
    max_response_bytes: int = Field(ge=1, le=HARD_MAX_HTTP_RESPONSE_BYTES)

    @classmethod
    def from_settings(cls) -> HTTPClientLimits:
        """Resolve safe HTTP limits from Django settings."""
        return cls(
            max_retry_delay_seconds=_bounded_positive_float_setting(
                "MICBOARD_HTTP_MAX_RETRY_DELAY_SECONDS",
                default=DEFAULT_HTTP_MAX_RETRY_DELAY_SECONDS,
                hard_limit=HARD_MAX_HTTP_RETRY_DELAY_SECONDS,
            ),
            max_response_bytes=_bounded_positive_int_setting(
                "MICBOARD_HTTP_MAX_RESPONSE_BYTES",
                default=DEFAULT_HTTP_MAX_RESPONSE_BYTES,
                hard_limit=HARD_MAX_HTTP_RESPONSE_BYTES,
            ),
        )


class SSEStreamLimits(PydanticBaseDTO):
    """Host-configured SSE limits constrained by package hard ceilings."""

    max_line_bytes: int = Field(ge=1, le=HARD_MAX_SSE_LINE_BYTES)
    max_event_bytes: int = Field(ge=1, le=HARD_MAX_SSE_EVENT_BYTES)

    @classmethod
    def from_settings(cls) -> SSEStreamLimits:
        """Resolve safe SSE limits from Django settings."""
        return cls(
            max_line_bytes=_bounded_positive_int_setting(
                "MICBOARD_SSE_MAX_LINE_BYTES",
                default=DEFAULT_SSE_MAX_LINE_BYTES,
                hard_limit=HARD_MAX_SSE_LINE_BYTES,
            ),
            max_event_bytes=_bounded_positive_int_setting(
                "MICBOARD_SSE_MAX_EVENT_BYTES",
                default=DEFAULT_SSE_MAX_EVENT_BYTES,
                hard_limit=HARD_MAX_SSE_EVENT_BYTES,
            ),
        )


def _bounded_positive_int_setting(name: str, *, default: int, hard_limit: int) -> int:
    """Parse a positive integer setting and enforce a package hard ceiling."""
    raw_value = getattr(settings, name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if parsed_value <= 0:
        return default
    return min(parsed_value, hard_limit)


def _bounded_positive_float_setting(
    name: str,
    *,
    default: float,
    hard_limit: float,
) -> float:
    """Parse a finite positive float setting and enforce a package hard ceiling."""
    raw_value = getattr(settings, name, default)
    if isinstance(raw_value, bool):
        return default
    try:
        parsed_value = float(raw_value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed_value) or parsed_value <= 0:
        return default
    return min(parsed_value, hard_limit)
