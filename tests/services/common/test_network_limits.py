"""Configuration contracts for bounded vendor network consumption."""

from __future__ import annotations

from django.test import override_settings

from micboard.services.common.network_limits import (
    DEFAULT_HTTP_MAX_RESPONSE_BYTES,
    DEFAULT_HTTP_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_SSE_MAX_EVENT_BYTES,
    DEFAULT_SSE_MAX_LINE_BYTES,
    HARD_MAX_HTTP_RESPONSE_BYTES,
    HARD_MAX_HTTP_RETRY_DELAY_SECONDS,
    HARD_MAX_SSE_EVENT_BYTES,
    HARD_MAX_SSE_LINE_BYTES,
    HTTPClientLimits,
    SSEStreamLimits,
)


@override_settings(
    MICBOARD_HTTP_MAX_RETRY_DELAY_SECONDS="999999",
    MICBOARD_HTTP_MAX_RESPONSE_BYTES=999999999,
    MICBOARD_SSE_MAX_LINE_BYTES=999999999,
    MICBOARD_SSE_MAX_EVENT_BYTES="999999999",
)
def test_network_settings_cannot_exceed_package_hard_limits() -> None:
    """Host configuration can lower, but never raise, package ceilings."""
    http_limits = HTTPClientLimits.from_settings()
    sse_limits = SSEStreamLimits.from_settings()

    assert http_limits.max_retry_delay_seconds == HARD_MAX_HTTP_RETRY_DELAY_SECONDS
    assert http_limits.max_response_bytes == HARD_MAX_HTTP_RESPONSE_BYTES
    assert sse_limits.max_line_bytes == HARD_MAX_SSE_LINE_BYTES
    assert sse_limits.max_event_bytes == HARD_MAX_SSE_EVENT_BYTES


@override_settings(
    MICBOARD_HTTP_MAX_RETRY_DELAY_SECONDS=float("nan"),
    MICBOARD_HTTP_MAX_RESPONSE_BYTES=False,
    MICBOARD_SSE_MAX_LINE_BYTES="invalid",
    MICBOARD_SSE_MAX_EVENT_BYTES=0,
)
def test_malformed_or_nonpositive_network_settings_use_safe_defaults() -> None:
    """Invalid host values fail closed to the documented bounded defaults."""
    http_limits = HTTPClientLimits.from_settings()
    sse_limits = SSEStreamLimits.from_settings()

    assert http_limits.max_retry_delay_seconds == DEFAULT_HTTP_MAX_RETRY_DELAY_SECONDS
    assert http_limits.max_response_bytes == DEFAULT_HTTP_MAX_RESPONSE_BYTES
    assert sse_limits.max_line_bytes == DEFAULT_SSE_MAX_LINE_BYTES
    assert sse_limits.max_event_bytes == DEFAULT_SSE_MAX_EVENT_BYTES
