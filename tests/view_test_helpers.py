"""Shared request and decorator helpers for focused view tests."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

from django.test import RequestFactory


def request(method: str = "get", path: str = "/", data: dict[str, str] | None = None) -> Any:
    """Build an authenticated request suitable for direct controller calls."""
    factory = RequestFactory()
    result = getattr(factory, method)(path, data or {})
    result.user = SimpleNamespace(is_authenticated=True, pk=7, username="alice")
    result.session = {}
    return result


def view(function: Any) -> Any:
    """Return the controller beneath authentication and method decorators."""
    return inspect.unwrap(function)
