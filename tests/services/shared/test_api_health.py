"""Request-path contracts for public manufacturer API health summaries."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

import pytest

from micboard.context_processors import api_health as api_health_context
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.telemetry.health import APIHealthLog
from micboard.services.manufacturer.plugin_registry import PluginRegistry
from micboard.services.shared import api_health
from micboard.services.shared.api_health_dtos import PUBLIC_API_HEALTH_ERROR


@pytest.fixture(autouse=True)
def clear_api_health_cache() -> None:
    """Keep aggregate and per-manufacturer snapshots isolated between tests."""
    cache.clear()


def _manufacturer(*, code: str, name: str | None = None) -> Manufacturer:
    return Manufacturer.objects.create(name=name or code.title(), code=code)


@pytest.mark.django_db
def test_context_uses_latest_persisted_snapshot_without_network_probe() -> None:
    """A render-time cache miss may query persistence but must never load a plugin."""
    manufacturer = _manufacturer(code="vendor")
    APIHealthLog.objects.create(
        manufacturer=manufacturer,
        status="unhealthy",
        response_time=0.25,
        error_message="https://operator:super-secret@example.test/health",
        details={"status": "unhealthy", "token": "super-secret"},
    )

    with patch.object(PluginRegistry, "get_plugin_class") as get_plugin:
        context = api_health_context(RequestFactory().get("/"))

    get_plugin.assert_not_called()
    result = context["api_health"]
    assert result["status"] == "unhealthy"
    assert result["details"][0]["details"] == {
        "status": "unhealthy",
        "response_time": 0.25,
        "error": PUBLIC_API_HEALTH_ERROR,
    }
    assert "super-secret" not in str(result)
    assert "operator" not in str(result)


@pytest.mark.django_db
def test_per_manufacturer_cache_snapshot_is_projected_to_safe_fields() -> None:
    """Cached producer payloads cannot leak credentials or arbitrary metadata."""
    _manufacturer(code="cached")
    cache.set(
        f"{api_health.API_HEALTH_SNAPSHOT_CACHE_PREFIX}cached",
        {
            "status": "error",
            "response_time": 0.5,
            "error": "request failed with password=hunter2",
            "api_key": "hunter2",
            "base_url": "https://user:hunter2@example.test",
        },
    )

    with patch.object(PluginRegistry, "get_plugin_class") as get_plugin:
        result = api_health.get_api_health()

    get_plugin.assert_not_called()
    assert result["details"][0]["details"] == {
        "status": "error",
        "response_time": 0.5,
        "error": PUBLIC_API_HEALTH_ERROR,
    }
    assert "hunter2" not in str(result)
    assert "example.test" not in str(result)


@pytest.mark.django_db
def test_latest_persisted_snapshot_wins_in_one_bounded_query(
    django_assert_num_queries,
) -> None:
    manufacturer = _manufacturer(code="latest")
    now = timezone.now()
    APIHealthLog.objects.create(
        manufacturer=manufacturer,
        timestamp=now - timedelta(minutes=1),
        status="unhealthy",
        details={"status": "unhealthy"},
    )
    APIHealthLog.objects.create(
        manufacturer=manufacturer,
        timestamp=now,
        status="healthy",
        response_time=0.1,
        details={"status": "healthy"},
    )

    with django_assert_num_queries(1):
        result = api_health.get_api_health()

    assert result["status"] == "healthy"
    assert result["details"][0]["details"] == {
        "status": "healthy",
        "response_time": 0.1,
    }


@pytest.mark.django_db
def test_unknown_snapshots_are_not_reported_as_failures() -> None:
    _manufacturer(code="not-probed")

    result = api_health.get_api_health()

    assert result["status"] == "unknown"
    assert result["healthy_manufacturers"] == 0
    assert result["details"][0]["status"] == "unknown"


@pytest.mark.django_db
def test_mixed_cached_snapshots_normalize_producer_variants() -> None:
    """Unknown payloads stay unknown while known failures get a safe public error."""
    for code in ("healthy", "offline", "invalid", "malformed"):
        _manufacturer(code=code)
    cache.set_many(
        {
            f"{api_health.API_HEALTH_SNAPSHOT_CACHE_PREFIX}healthy": {
                "status": "healthy",
                "response_time": -1,
            },
            f"{api_health.API_HEALTH_SNAPSHOT_CACHE_PREFIX}offline": {"status": "offline"},
            f"{api_health.API_HEALTH_SNAPSHOT_CACHE_PREFIX}invalid": {
                "status": "unexpected",
                "response_time": True,
            },
            f"{api_health.API_HEALTH_SNAPSHOT_CACHE_PREFIX}malformed": "not-a-mapping",
        }
    )

    result = api_health.get_api_health()

    assert result["status"] == "partial"
    assert result["healthy_manufacturers"] == 1
    by_code = {detail["code"]: detail["details"] for detail in result["details"]}
    assert by_code["healthy"] == {"status": "healthy"}
    assert by_code["offline"] == {
        "status": "offline",
        "error": PUBLIC_API_HEALTH_ERROR,
    }
    assert by_code["invalid"] == {"status": "unknown"}
    assert by_code["malformed"] == {"status": "unknown"}


def test_snapshot_sanitizer_rejects_non_string_status_and_non_finite_timing() -> None:
    snapshot = api_health.sanitize_public_api_health_snapshot(
        {"status": 200, "response_time": float("inf")}
    )

    assert snapshot.model_dump(exclude_none=True) == {"status": "unknown"}


@pytest.mark.django_db
def test_public_summary_caps_manufacturers() -> None:
    Manufacturer.objects.bulk_create(
        [
            Manufacturer(name=f"Vendor {index:03}", code=f"v{index:03}")
            for index in range(api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS + 1)
        ]
    )

    result = api_health.get_api_health()

    assert result["total_manufacturers"] == api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS
    assert len(result["details"]) == api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS
    assert result["truncated"] is True


@pytest.mark.django_db
def test_valid_aggregate_cache_avoids_database_access() -> None:
    cached = {
        "status": "unhealthy",
        "details": [
            {
                "manufacturer": "Cached",
                "code": "cached",
                "status": "error",
                "details": {
                    "status": "error",
                    "error": "token=must-not-leak",
                },
            }
        ],
        "total_manufacturers": 1,
        "healthy_manufacturers": 0,
        "truncated": False,
    }
    cache.set(api_health.API_HEALTH_AGGREGATE_CACHE_KEY, cached)

    with patch.object(api_health.Manufacturer.objects, "filter") as query:
        result = api_health.get_api_health()

    query.assert_not_called()
    assert result["details"][0]["details"]["error"] == PUBLIC_API_HEALTH_ERROR
    assert "must-not-leak" not in str(result)


@pytest.mark.django_db
def test_invalid_aggregate_cache_rebuilds_from_persistence() -> None:
    _manufacturer(code="fallback")
    cache.set(api_health.API_HEALTH_AGGREGATE_CACHE_KEY, {"status": "bogus"})

    result = api_health.get_api_health()

    assert result["status"] == "unknown"
    assert result["total_manufacturers"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cached",
    [
        {
            "status": "unknown",
            "details": [],
            "total_manufacturers": 1,
            "healthy_manufacturers": 0,
        },
        {
            "status": "unconfigured",
            "details": [],
            "total_manufacturers": 0,
            "healthy_manufacturers": 1,
        },
    ],
)
def test_inconsistent_aggregate_cache_rebuilds_from_persistence(
    cached: dict[str, object],
) -> None:
    manufacturer = _manufacturer(code="consistent-fallback")
    cache.set(api_health.API_HEALTH_AGGREGATE_CACHE_KEY, cached)

    result = api_health.get_api_health()

    assert result["details"][0]["code"] == manufacturer.code
    assert result["total_manufacturers"] == 1


@pytest.mark.django_db
def test_oversized_aggregate_cache_rebuilds_from_bounded_persistence() -> None:
    manufacturer = _manufacturer(code="bounded-fallback")
    detail = {
        "manufacturer": "Cached",
        "code": "cached",
        "status": "healthy",
        "details": {"status": "healthy"},
    }
    cache.set(
        api_health.API_HEALTH_AGGREGATE_CACHE_KEY,
        {
            "status": "healthy",
            "details": [detail] * (api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS + 1),
            "total_manufacturers": api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS + 1,
            "healthy_manufacturers": api_health.MAX_PUBLIC_API_HEALTH_MANUFACTURERS + 1,
            "truncated": False,
        },
    )

    result = api_health.get_api_health()

    assert result["total_manufacturers"] == 1
    assert result["details"][0]["code"] == manufacturer.code
    assert result["status"] == "unknown"


@pytest.mark.django_db
def test_empty_configuration_is_unconfigured() -> None:
    result = api_health.get_api_health()

    assert result == {
        "status": "unconfigured",
        "details": [],
        "total_manufacturers": 0,
        "healthy_manufacturers": 0,
        "truncated": False,
    }
