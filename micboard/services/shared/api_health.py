"""Cache-only API health aggregation for public request rendering."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any, cast

from django.core.cache import cache
from django.db.models import OuterRef, QuerySet, Subquery

from pydantic import ValidationError

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.telemetry.health import APIHealthLog
from micboard.services.manufacturer.secret_redaction import redact_secrets
from micboard.services.shared.api_health_dtos import (
    MAX_PUBLIC_API_HEALTH_MANUFACTURERS,
    AggregateHealthStatus,
    APIHealthSummary,
    ManufacturerAPIHealthSnapshot,
    ManufacturerHealthStatus,
    PublicAPIHealthSnapshot,
)

API_HEALTH_AGGREGATE_CACHE_KEY = "micboard:api-health:aggregate:v2"
API_HEALTH_SNAPSHOT_CACHE_PREFIX = "api_health_"
API_HEALTH_AGGREGATE_CACHE_SECONDS = 30

_MANUFACTURER_STATUSES = frozenset(
    {"healthy", "unhealthy", "degraded", "offline", "error", "unknown"}
)
_FAILURE_STATUSES = frozenset({"unhealthy", "degraded", "offline", "error"})


def _normalize_status(value: object) -> ManufacturerHealthStatus:
    if not isinstance(value, str):
        return "unknown"
    normalized = value[:32].strip().lower()
    if normalized not in _MANUFACTURER_STATUSES:
        return "unknown"
    return cast(ManufacturerHealthStatus, normalized)


def sanitize_public_api_health_snapshot(value: object) -> PublicAPIHealthSnapshot:
    """Project arbitrary producer data onto bounded, secret-safe public fields."""
    if not isinstance(value, Mapping):
        return PublicAPIHealthSnapshot(status="unknown")

    raw_response_time = value.get("response_time")
    response_time = (
        raw_response_time
        if isinstance(raw_response_time, int | float)
        and not isinstance(raw_response_time, bool)
        and isfinite(raw_response_time)
        and raw_response_time >= 0
        else None
    )
    raw_status = value.get("status")
    redacted = redact_secrets(
        {
            "status": raw_status[:32] if isinstance(raw_status, str) else None,
            "response_time": response_time,
            "error": bool(value.get("error") or value.get("error_message")),
        }
    )
    status = _normalize_status(redacted.get("status"))
    error = redacted.get("error")
    if status in _FAILURE_STATUSES and not error:
        error = True
    return PublicAPIHealthSnapshot(
        status=status,
        response_time=response_time,
        error=error,
    )


def _aggregate(
    details: list[ManufacturerAPIHealthSnapshot], *, truncated: bool
) -> APIHealthSummary:
    total_count = len(details)
    healthy_count = sum(detail.status == "healthy" for detail in details)
    known_count = sum(detail.status != "unknown" for detail in details)

    status: AggregateHealthStatus
    if total_count == 0:
        status = "unconfigured"
    elif known_count == 0:
        status = "unknown"
    elif healthy_count == total_count:
        status = "healthy"
    elif healthy_count:
        status = "partial"
    else:
        status = "unhealthy"

    return APIHealthSummary(
        status=status,
        details=details,
        total_manufacturers=total_count,
        healthy_manufacturers=healthy_count,
        truncated=truncated,
    )


def _manufacturer_snapshot_queryset() -> QuerySet[Manufacturer]:
    """Return active manufacturers annotated with their latest persisted observation."""
    latest_log = APIHealthLog.objects.filter(manufacturer_id=OuterRef("pk")).order_by(
        "-timestamp", "-pk"
    )
    return (
        Manufacturer.objects.filter(is_active=True)
        .only("id", "name", "code")
        .annotate(
            latest_health_status=Subquery(latest_log.values("status")[:1]),
            latest_health_response_time=Subquery(latest_log.values("response_time")[:1]),
            latest_health_error=Subquery(latest_log.values("error_message")[:1]),
        )
        .order_by("name", "pk")
    )


def _persisted_snapshot(manufacturer: Manufacturer) -> dict[str, Any]:
    status = getattr(manufacturer, "latest_health_status", None)
    if status is None:
        return {"status": "unknown"}
    snapshot = {
        "status": status,
        "response_time": getattr(manufacturer, "latest_health_response_time", None),
    }
    error = getattr(manufacturer, "latest_health_error", "")
    if error:
        snapshot["error"] = error
    return snapshot


def _load_summary() -> APIHealthSummary:
    manufacturers = list(
        _manufacturer_snapshot_queryset()[: MAX_PUBLIC_API_HEALTH_MANUFACTURERS + 1]
    )
    truncated = len(manufacturers) > MAX_PUBLIC_API_HEALTH_MANUFACTURERS
    manufacturers = manufacturers[:MAX_PUBLIC_API_HEALTH_MANUFACTURERS]

    cache_keys = {
        manufacturer.pk: f"{API_HEALTH_SNAPSHOT_CACHE_PREFIX}{manufacturer.code}"
        for manufacturer in manufacturers
    }
    cached_snapshots = cache.get_many(cache_keys.values())
    details: list[ManufacturerAPIHealthSnapshot] = []
    for manufacturer in manufacturers:
        cache_key = cache_keys[manufacturer.pk]
        source = cached_snapshots.get(cache_key)
        if source is None:
            source = _persisted_snapshot(manufacturer)
        public_snapshot = sanitize_public_api_health_snapshot(source)
        details.append(
            ManufacturerAPIHealthSnapshot(
                manufacturer=manufacturer.name,
                code=manufacturer.code,
                status=public_snapshot.status,
                details=public_snapshot,
            )
        )
    return _aggregate(details, truncated=truncated)


def get_api_health() -> dict[str, Any]:
    """Return bounded cached/persisted health without external request-time probes."""
    cached_result = cache.get(API_HEALTH_AGGREGATE_CACHE_KEY)
    if cached_result is not None:
        try:
            summary = APIHealthSummary.model_validate(cached_result)
        except ValidationError:
            pass
        else:
            return summary.model_dump(exclude_none=True)

    summary = _load_summary()
    result = summary.model_dump(exclude_none=True)
    cache.set(
        API_HEALTH_AGGREGATE_CACHE_KEY,
        result,
        timeout=API_HEALTH_AGGREGATE_CACHE_SECONDS,
    )
    return result
