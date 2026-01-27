"""Metrics collection for django-micboard services.

Provides utilities for tracking service performance and usage.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List

from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class ServiceMetric:
    """Represents a service operation metric."""

    service_name: str
    method_name: str
    duration_ms: float
    timestamp: datetime
    success: bool
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsCollector:
    """Collects and stores service metrics."""

    METRICS_KEY_PREFIX = "micboard:metrics:"
    METRICS_TTL = 3600  # 1 hour

    @classmethod
    def record_metric(cls, metric: ServiceMetric) -> None:
        """Record a service metric.

        Args:
            metric: ServiceMetric instance to record.
        """
        # Store in cache for short-term analysis
        key = f"{cls.METRICS_KEY_PREFIX}{metric.service_name}:{metric.method_name}"

        try:
            metrics = cache.get(key, [])
            metrics.append(
                {
                    "duration_ms": metric.duration_ms,
                    "timestamp": metric.timestamp.isoformat(),
                    "success": metric.success,
                    "error_message": metric.error_message,
                    "metadata": metric.metadata,
                }
            )

            # Keep only last 100 metrics per method
            if len(metrics) > 100:
                metrics = metrics[-100:]

            cache.set(key, metrics, cls.METRICS_TTL)

        except Exception as e:
            logger.error(f"Error recording metric: {e}")

    @classmethod
    def get_metrics(cls, *, service_name: str, method_name: str) -> List[Dict[str, Any]]:
        """Get metrics for specific service method.

        Args:
            service_name: Service class name.
            method_name: Method name.

        Returns:
            List of metric dictionaries.
        """
        key = f"{cls.METRICS_KEY_PREFIX}{service_name}:{method_name}"
        return cache.get(key, [])

    @classmethod
    def get_service_metrics(cls, *, service_name: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get all metrics for a service.

        Args:
            service_name: Service class name.

        Returns:
            Dictionary of method names to metric lists.
        """
        # This would require cache backend with pattern matching
        # For now, return empty dict
        return {}

    @classmethod
    def calculate_stats(cls, *, service_name: str, method_name: str) -> Dict[str, Any]:
        """Calculate statistics for service method.

        Args:
            service_name: Service class name.
            method_name: Method name.

        Returns:
            Dictionary with statistics (avg, min, max, success_rate).
        """
        metrics = cls.get_metrics(service_name=service_name, method_name=method_name)

        if not metrics:
            return {
                "count": 0,
                "avg_duration_ms": 0,
                "min_duration_ms": 0,
                "max_duration_ms": 0,
                "success_rate": 0,
            }

        durations = [m["duration_ms"] for m in metrics]
        successes = sum(1 for m in metrics if m["success"])

        return {
            "count": len(metrics),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "success_rate": (successes / len(metrics)) * 100,
        }


def track_service_metrics(func: Callable) -> Callable:
    """Decorator to track service method metrics.

    Example:
        class HardwareService:
            @track_service_metrics
            @staticmethod
            def get_active_receivers() -> QuerySet:
                return WirelessChassis.objects.filter(is_online=True)
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        service_name = func.__qualname__.split(".")[0]
        method_name = func.__name__
        success = True
        error_message = ""

        try:
            result = func(*args, **kwargs)
            return result

        except Exception as e:
            success = False
            error_message = str(e)
            raise

        finally:
            duration_ms = (time.time() - start_time) * 1000

            metric = ServiceMetric(
                service_name=service_name,
                method_name=method_name,
                duration_ms=duration_ms,
                timestamp=datetime.now(),
                success=success,
                error_message=error_message,
            )

            MetricsCollector.record_metric(metric)

            # Log slow operations
            if duration_ms > 1000:  # > 1 second
                logger.warning(
                    f"SLOW SERVICE CALL: {service_name}.{method_name} took {duration_ms:.2f}ms"
                )

    return wrapper


@contextmanager
def measure_operation(operation_name: str):
    """Context manager to measure operation duration.

    Args:
        operation_name: Name of operation being measured.

    Example:
        with measure_operation("database_query"):
            results = Model.objects.filter(...).all()
    """
    start_time = time.time()

    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        logger.debug(f"{operation_name} took {duration_ms:.2f}ms")


class PerformanceMonitor:
    """Monitor performance of code blocks."""

    def __init__(self, name: str):
        """Initialize monitor.

        Args:
            name: Name of the monitored operation.
        """
        self.name = name
        self.start_time = None

    def __enter__(self):
        """Start monitoring."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop monitoring and log results."""
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000

            if exc_type is None:
                logger.info(f"✓ {self.name}: {duration_ms:.2f}ms")
            else:
                logger.error(f"✗ {self.name}: {duration_ms:.2f}ms (failed)")
