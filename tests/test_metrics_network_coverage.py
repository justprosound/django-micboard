"""Metrics behavior and failure-path coverage."""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import Mock

import pytest

from micboard import metrics as metrics_module
from micboard.metrics import (
    MetricsCollector,
    PerformanceMonitor,
    ServiceMetric,
    measure_operation,
    track_service_metrics,
)


def _metric(*, success: bool = True) -> ServiceMetric:
    return ServiceMetric(
        service_name="Inventory",
        method_name="refresh",
        duration_ms=10.0,
        timestamp=datetime(2026, 1, 1),
        success=success,
        error_message="" if success else "failed",
        metadata={"site": 1},
    )


class Inventory:
    """Top-level service used to preserve the decorator's service-name contract."""

    @track_service_metrics
    def refresh(self, value: int) -> int:
        return value * 2

    @track_service_metrics
    def fail(self) -> None:
        raise RuntimeError("broken")


def test_record_metric_appends_trims_and_survives_cache_failure(monkeypatch, caplog) -> None:
    existing = [{"duration_ms": value} for value in range(100)]
    cache_get = Mock(return_value=existing)
    cache_set = Mock()
    monkeypatch.setattr(metrics_module.cache, "get", cache_get)
    monkeypatch.setattr(metrics_module.cache, "set", cache_set)

    MetricsCollector.record_metric(_metric())

    stored = cache_set.call_args.args[1]
    assert len(stored) == 100
    assert stored[-1]["duration_ms"] == 10.0
    assert stored[-1]["timestamp"] == "2026-01-01T00:00:00"

    cache_get.side_effect = RuntimeError("cache down")
    with caplog.at_level(logging.ERROR):
        MetricsCollector.record_metric(_metric())
    assert "Error recording service metric" in caplog.text
    assert "cache down" not in caplog.text

    cache_get.side_effect = None
    cache_get.return_value = []
    cache_set.side_effect = None
    MetricsCollector.record_metric(_metric())
    assert cache_set.call_args.args[1][0]["duration_ms"] == 10.0


def test_metric_queries_and_statistics(monkeypatch) -> None:
    cache_get = Mock(return_value=[])
    monkeypatch.setattr(metrics_module.cache, "get", cache_get)
    assert MetricsCollector.get_metrics(service_name="Inventory", method_name="refresh") == []
    assert MetricsCollector.get_service_metrics(service_name="Inventory") == {}
    assert MetricsCollector.calculate_stats(service_name="Inventory", method_name="refresh") == {
        "count": 0,
        "avg_duration_ms": 0,
        "min_duration_ms": 0,
        "max_duration_ms": 0,
        "success_rate": 0,
    }

    cache_get.return_value = [
        {"duration_ms": 10.0, "success": True},
        {"duration_ms": 30.0, "success": False},
    ]
    assert MetricsCollector.calculate_stats(service_name="Inventory", method_name="refresh") == {
        "count": 2,
        "avg_duration_ms": 20.0,
        "min_duration_ms": 10.0,
        "max_duration_ms": 30.0,
        "success_rate": 50.0,
    }


def test_metric_decorator_records_success_failure_and_slow_call(monkeypatch, caplog) -> None:
    clock = iter([1.0, 1.01, 2.0, 3.5])
    monkeypatch.setattr(metrics_module.time, "time", lambda: next(clock))
    record = Mock()
    monkeypatch.setattr(MetricsCollector, "record_metric", record)

    inventory = Inventory()
    assert inventory.refresh(3) == 6
    success_metric = record.call_args_list[0].args[0]
    assert success_metric.service_name == "Inventory"
    assert success_metric.method_name == "refresh"
    assert success_metric.success is True

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError, match="broken"):
        inventory.fail()
    failure_metric = record.call_args_list[1].args[0]
    assert failure_metric.success is False
    assert failure_metric.error_message == "RuntimeError: service error details redacted"
    assert "broken" not in failure_metric.error_message
    assert "SLOW SERVICE CALL" in caplog.text


def test_measure_operation_logs_even_when_body_raises(monkeypatch, caplog) -> None:
    clock = iter([10.0, 10.25])
    monkeypatch.setattr(metrics_module.time, "time", lambda: next(clock))
    with (
        caplog.at_level(logging.DEBUG, logger=metrics_module.__name__),
        pytest.raises(ValueError, match="bad"),
        measure_operation("query"),
    ):
        raise ValueError("bad")
    assert "query took 250.00ms" in caplog.text


def test_performance_monitor_logs_success_failure_and_unstarted(monkeypatch, caplog) -> None:
    clock = iter([20.0, 20.1, 30.0, 30.2])
    monkeypatch.setattr(metrics_module.time, "time", lambda: next(clock))
    with (
        caplog.at_level(logging.INFO, logger=metrics_module.__name__),
        PerformanceMonitor("success") as monitor,
    ):
        assert monitor.start_time == 20.0
    assert "success: 100.00ms" in caplog.text

    with (
        caplog.at_level(logging.ERROR, logger=metrics_module.__name__),
        pytest.raises(RuntimeError),
        PerformanceMonitor("failure"),
    ):
        raise RuntimeError("failed")
    assert "failure: 200.00ms (failed)" in caplog.text

    PerformanceMonitor("never-started").__exit__(None, None, None)
