from __future__ import annotations

import logging
import time

from .exceptions import APIError

logger = logging.getLogger(__name__)


class CircuitOpenError(APIError):
    """Raised when a circuit breaker is open for an endpoint."""


class CircuitBreaker:
    def __init__(
        self, *, name: str | None = None, failure_threshold: int = 5, recovery_timeout: int = 60
    ):
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout = int(recovery_timeout)
        self._failures = 0
        self._last_failure = 0.0
        self._state = "closed"

    def allow_request(self) -> bool:
        if self._state == "open":
            if (time.time() - self._last_failure) > self.recovery_timeout:
                self._state = "half-open"
                logger.info("Circuit half-open for %s", self.name or "unknown")
                return True
            return False
        return True

    def record_success(self) -> None:
        prev = self._state
        self._failures = 0
        self._state = "closed"
        if prev in ("open", "half-open"):
            logger.info("Circuit closed for %s", self.name or "unknown")
            try:
                from datetime import datetime

                from micboard.metrics import MetricsCollector, ServiceMetric

                MetricsCollector.record_metric(
                    ServiceMetric(
                        service_name=self.name or "external_api",
                        method_name="circuit_closed",
                        duration_ms=0.0,
                        timestamp=datetime.now(),
                        success=True,
                    )
                )
            except Exception:
                logger.debug("Metrics recording for circuit_closed failed", exc_info=True)

    def record_failure(self) -> None:
        prev = self._state
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "open"
            if prev != "open":
                logger.warning(
                    "Circuit opened for %s after %d failures",
                    self.name or "external_api",
                    self._failures,
                )
                try:
                    from datetime import datetime

                    from micboard.metrics import MetricsCollector, ServiceMetric

                    MetricsCollector.record_metric(
                        ServiceMetric(
                            service_name=self.name or "external_api",
                            method_name="circuit_open",
                            duration_ms=0.0,
                            timestamp=datetime.now(),
                            success=False,
                            error_message="failure_threshold_exceeded",
                            metadata={"failures": self._failures},
                        )
                    )
                except Exception:
                    logger.debug("Metrics recording for circuit_open failed", exc_info=True)

    @property
    def state(self) -> str:
        return self._state
