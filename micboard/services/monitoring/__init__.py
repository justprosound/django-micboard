"""Monitoring and health services for django-micboard.

This package contains services for:
- Device health monitoring and metrics
- Connection health and validation
- Alert generation and notification
- Uptime tracking
- Access control for monitoring views
"""

from __future__ import annotations

from .alerts import AlertManager, check_hardware_offline_alerts, check_transmitter_alerts
from .base_health_mixin import AggregatedHealthChecker, HealthCheckMixin
from .connection import ConnectionHealthService
from .connection_validation import ConnectionValidationService
from .monitoring_access import MonitoringService as AccessControlService
from .monitoring_service import MonitoringService
from .uptime_service import BulkUptimeCalculator, UptimeService

__all__ = [
    "AccessControlService",
    "AggregatedHealthChecker",
    "AlertManager",
    "BulkUptimeCalculator",
    "ConnectionHealthService",
    "ConnectionValidationService",
    "HealthCheckMixin",
    "MonitoringService",
    "UptimeService",
    "check_hardware_offline_alerts",
    "check_transmitter_alerts",
    "acknowledge_alert",
    "resolve_alert",
]
