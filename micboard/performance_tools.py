"""Performance analysis and optimization tools.

Provides utilities to analyze and optimize service layer performance.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List

from django.db import connection, reset_queries


@dataclass
class PerformanceReport:
    """Report on performance metrics."""

    operation_name: str
    duration_ms: float
    query_count: int
    cache_hits: int = 0
    cache_misses: int = 0
    peak_memory_mb: float = 0.0
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def success(self) -> bool:
        """Check if operation was successful."""
        return len(self.errors) == 0

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100

    def __str__(self) -> str:
        """String representation."""
        status = "✓" if self.success else "✗"
        return (
            f"{status} {self.operation_name}: {self.duration_ms:.2f}ms ({self.query_count} queries)"
        )


class PerformanceAnalyzer:
    """Analyze performance of service operations."""

    @staticmethod
    @contextmanager
    def analyze(operation_name: str, *, analyze_queries: bool = True):
        """Context manager to analyze performance.

        Args:
            operation_name: Name of operation being analyzed.
            analyze_queries: Whether to capture SQL queries.

        Yields:
            PerformanceReport instance.
        """
        report = PerformanceReport(operation_name=operation_name, duration_ms=0, query_count=0)

        if analyze_queries:
            reset_queries()

        start_time = time.time()
        start_queries = len(connection.queries) if analyze_queries else 0

        try:
            yield report
        except Exception as e:
            report.errors.append(str(e))
            raise
        finally:
            report.duration_ms = (time.time() - start_time) * 1000

            if analyze_queries:
                report.query_count = len(connection.queries) - start_queries

    @staticmethod
    def profile_service_method(func: Callable, *args, **kwargs) -> tuple[Any, PerformanceReport]:
        """Profile a service method.

        Args:
            func: Function to profile.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Tuple of (result, PerformanceReport).
        """
        with PerformanceAnalyzer.analyze(func.__name__) as report:
            result = func(*args, **kwargs)

        return result, report

    @staticmethod
    def get_slow_queries(*, threshold_ms: float = 100) -> List[Dict[str, str]]:
        """Get queries slower than threshold.

        Args:
            threshold_ms: Time threshold in milliseconds.

        Returns:
            List of slow queries.
        """
        slow = []
        for query in connection.queries:
            duration_ms = float(query["time"]) * 1000
            if duration_ms > threshold_ms:
                slow.append(
                    {
                        "sql": query["sql"],
                        "time_ms": f"{duration_ms:.2f}",
                    }
                )
        return slow


class DatabaseHealthCheck:
    """Check database health and performance."""

    @staticmethod
    def connection_pool_status() -> Dict[str, Any]:
        """Check database connection pool status.

        Returns:
            Dictionary with connection pool info.
        """
        return {
            "total_queries": len(connection.queries),
            "query_count_since_reset": len(connection.queries),
            "in_atomic_block": connection.in_atomic_block,
        }

    @staticmethod
    def query_efficiency_report() -> Dict[str, Any]:
        """Generate query efficiency report.

        Returns:
            Dictionary with efficiency metrics.
        """
        if not connection.queries:
            return {"status": "No queries executed"}

        queries = connection.queries
        total_time = sum(float(q["time"]) for q in queries)
        avg_time = total_time / len(queries)

        slow_queries = [q for q in queries if float(q["time"]) > avg_time * 2]

        return {
            "total_queries": len(queries),
            "total_time_ms": f"{total_time * 1000:.2f}",
            "avg_time_ms": f"{avg_time * 1000:.2f}",
            "slow_query_count": len(slow_queries),
            "slow_queries": [
                {"sql": q["sql"][:100] + "...", "time_ms": f"{float(q['time']) * 1000:.2f}"}
                for q in slow_queries[:5]  # Top 5
            ],
        }


class BenchmarkRunner:
    """Run benchmarks on service operations."""

    @staticmethod
    def benchmark(func: Callable, *args, iterations: int = 100, **kwargs) -> Dict[str, Any]:
        """Run benchmark on function.

        Args:
            func: Function to benchmark.
            *args: Function arguments.
            iterations: Number of iterations.
            **kwargs: Function keyword arguments.

        Returns:
            Benchmark results.
        """
        times = []

        for _ in range(iterations):
            start = time.time()
            try:
                func(*args, **kwargs)
                times.append((time.time() - start) * 1000)
            except Exception:
                pass

        if not times:
            return {"error": "No successful executions"}

        times.sort()
        return {
            "iterations": len(times),
            "avg_ms": sum(times) / len(times),
            "min_ms": times[0],
            "max_ms": times[-1],
            "median_ms": times[len(times) // 2],
            "p95_ms": times[int(len(times) * 0.95)],
            "p99_ms": times[int(len(times) * 0.99)],
        }

    @staticmethod
    def compare_implementations(
        old_func: Callable, new_func: Callable, *args, iterations: int = 100, **kwargs
    ) -> Dict[str, Any]:
        """Compare two implementations.

        Args:
            old_func: Original implementation.
            new_func: New implementation.
            *args: Function arguments.
            iterations: Number of iterations.
            **kwargs: Function keyword arguments.

        Returns:
            Comparison results.
        """
        old_results = BenchmarkRunner.benchmark(old_func, *args, iterations=iterations, **kwargs)

        new_results = BenchmarkRunner.benchmark(new_func, *args, iterations=iterations, **kwargs)

        if "error" in old_results or "error" in new_results:
            return {"error": "Benchmark failed"}

        improvement = (
            (old_results["avg_ms"] - new_results["avg_ms"]) / old_results["avg_ms"]
        ) * 100

        return {
            "old_avg_ms": f"{old_results['avg_ms']:.2f}",
            "new_avg_ms": f"{new_results['avg_ms']:.2f}",
            "improvement_percent": f"{improvement:.1f}%",
            "speedup": f"{old_results['avg_ms'] / new_results['avg_ms']:.2f}x",
        }


class LoadTestSimulator:
    """Simulate load testing scenarios."""

    @staticmethod
    def simulate_concurrent_requests(
        func: Callable, concurrent_count: int = 10, *args, **kwargs
    ) -> Dict[str, Any]:
        """Simulate concurrent requests.

        Args:
            func: Function to test.
            concurrent_count: Number of concurrent requests.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Load test results.
        """
        import concurrent.futures

        results = {"successful": 0, "failed": 0, "errors": []}
        times = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_count) as executor:
            futures = [executor.submit(func, *args, **kwargs) for _ in range(concurrent_count)]

            start_time = time.time()

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                    results["successful"] += 1
                    times.append(time.time() - start_time)
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(str(e))

        total_time = time.time() - start_time

        return {
            "concurrent_count": concurrent_count,
            "total_time_s": f"{total_time:.2f}",
            "successful": results["successful"],
            "failed": results["failed"],
            "throughput_per_second": f"{concurrent_count / total_time:.2f}",
            "avg_response_time_ms": f"{(total_time * 1000) / concurrent_count:.2f}",
            "errors": results["errors"][:5],  # Top 5 errors
        }
