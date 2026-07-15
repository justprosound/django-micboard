"""Standardized health-check contracts."""

from __future__ import annotations

import logging

import pytest

from micboard.services.monitoring.base_health_mixin import HealthCheckMixin


class _Checker(HealthCheckMixin):
    def __init__(self, result: dict | Exception):
        self.result = result

    def check_health(self) -> dict:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_base_health_check_requires_implementation() -> None:
    """Consumers cannot silently use the mixin without a resource-specific probe."""
    with pytest.raises(NotImplementedError):
        HealthCheckMixin().check_health()


def test_standard_response_includes_optional_context_and_validates_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Health results share one timestamped shape and reject invented states."""
    checker = _Checker({})
    response = checker._standardize_health_response(
        status="healthy",
        details={"latency_ms": 4},
        error="warning",
    )

    assert response["status"] == "healthy"
    assert response["details"] == {"latency_ms": 4}
    assert response["error"] == "warning"
    assert response["timestamp"]

    with caplog.at_level(logging.WARNING):
        invalid = checker._standardize_health_response(status="invented")
    assert invalid["status"] == "unknown"
    assert "details" not in invalid
    assert "error" not in invalid
    assert "Invalid health status" in caplog.messages[0]


def test_empty_health_response_is_an_error() -> None:
    """An absent upstream payload is distinguishable from an unknown state."""
    response = _Checker({})._parse_health_response({})

    assert response["status"] == "error"
    assert response["error"] == "Empty health response"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "OK"}, "healthy"),
        ({"status": "up"}, "healthy"),
        ({"status": "partial"}, "degraded"),
        ({"status": "down"}, "unhealthy"),
        ({"status": "unexpected"}, "unknown"),
        ({"healthy": True}, "healthy"),
        ({"is_healthy": False}, "unhealthy"),
        ({"api_healthy": True}, "healthy"),
        ({"status": 1}, "unknown"),
        ({"latency_ms": 8}, "unknown"),
    ],
)
def test_parser_normalizes_manufacturer_status_shapes(payload: dict, expected: str) -> None:
    """Common status aliases and types map onto the stable health vocabulary."""
    assert _Checker({})._parse_health_response(payload)["status"] == expected


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"status": "down", "error": "direct"}, "direct"),
        ({"status": "down", "error_message": "alternate"}, "alternate"),
        ({"status": "down", "message": "fallback"}, "fallback"),
    ],
)
def test_parser_extracts_errors_and_retains_unrecognized_detail(
    payload: dict,
    expected_error: str,
) -> None:
    """Error aliases normalize while manufacturer-specific context remains available."""
    payload["latency_ms"] = 8

    response = _Checker({})._parse_health_response(payload)

    assert response["error"] == expected_error
    assert response["details"]["latency_ms"] == 8
    assert "status" not in response["details"]


@pytest.mark.parametrize(
    ("result", "healthy"),
    [
        ({"status": "healthy"}, True),
        ({"status": "degraded"}, False),
        ({"status": "unhealthy"}, False),
        ({"status": "error"}, False),
        ({}, False),
    ],
)
def test_health_predicates_follow_standard_status(
    result: dict,
    healthy: bool,
) -> None:
    """The health predicate remains a direct projection of the standardized result."""
    checker = _Checker(result)

    assert checker.is_healthy() is healthy
