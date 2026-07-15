"""Secret-safe exception metadata for application logs."""

from __future__ import annotations

from types import TracebackType


def sanitized_exception_info(
    exc: Exception,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    """Keep traceback context while replacing credential-bearing exception text."""
    safe_exception = RuntimeError(f"{type(exc).__name__}: error details redacted")
    return RuntimeError, safe_exception, exc.__traceback__
