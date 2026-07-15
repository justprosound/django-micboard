"""Coverage for UI middleware, decorators, and template helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.http import HttpResponse

import pytest

from micboard.context_processors import api_health
from micboard.decorators import rate_limit_user, rate_limit_view
from micboard.templatetags.micboard_tags import get_item, wireless_battery_percentage


@patch("micboard.context_processors.get_api_health", return_value={"vendor": "healthy"})
def test_api_health_context_processor_delegates(mock_health: MagicMock) -> None:
    assert api_health(SimpleNamespace()) == {"api_health": {"vendor": "healthy"}}
    mock_health.assert_called_once_with()


@pytest.mark.parametrize(
    ("dictionary", "key", "expected"),
    [(None, "missing", None), ({}, "missing", None), ({"answer": 42}, "answer", 42)],
)
def test_get_item_handles_empty_and_populated_mappings(
    dictionary: dict[str, int] | None, key: str, expected: int | None
) -> None:
    assert get_item(dictionary, key) == expected


@patch("micboard.templatetags.micboard_tags.get_battery_percentage", return_value=73)
def test_wireless_battery_percentage_handles_none_and_delegates(
    get_percentage: MagicMock,
) -> None:
    assert wireless_battery_percentage(None) is None
    unit = object()
    assert wireless_battery_percentage(unit) == 73
    get_percentage.assert_called_once_with(unit)


def test_rate_limit_view_allows_default_ip_key() -> None:
    request = SimpleNamespace()
    view = Mock(return_value=HttpResponse("ok"), __name__="sample_view")

    with (
        patch("micboard.decorators.get_client_ip", return_value="192.0.2.5"),
        patch("micboard.decorators.check_rate_limit", return_value=(True, 0, 1)) as check,
    ):
        response = rate_limit_view(max_requests=2, window_seconds=10)(view)(request, 4, flag=True)

    assert response.content == b"ok"
    check.assert_called_once_with("rate_limit_sample_view_192.0.2.5", 2, 10)
    view.assert_called_once_with(request, 4, flag=True)


def test_rate_limit_view_rejects_custom_key_with_retry_header() -> None:
    request = SimpleNamespace()
    key_func = Mock(return_value="custom-key")
    view = Mock(__name__="sample_view")

    with patch("micboard.decorators.check_rate_limit", return_value=(False, 17, 2)):
        response = rate_limit_view(4, 30, key_func)(view)(request)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert json.loads(response.content) == {
        "error": "Rate limit exceeded",
        "detail": "Maximum 4 requests per 30 seconds",
        "retry_after": 17,
    }
    key_func.assert_called_once_with(request)
    view.assert_not_called()


def test_rate_limit_user_uses_authenticated_user_key() -> None:
    request = SimpleNamespace(user=SimpleNamespace(pk=3))
    view = Mock(return_value=HttpResponse("ok"), __name__="protected")

    with (
        patch("micboard.decorators.get_user_cache_key", return_value="user:3") as get_key,
        patch("micboard.decorators.check_rate_limit", return_value=(True, 0, 1)) as check,
    ):
        response = rate_limit_user(8, 45)(view)(request)

    assert response.status_code == 200
    get_key.assert_called_once_with(request, view_func_name="protected")
    check.assert_called_once_with("user:3", 8, 45)
