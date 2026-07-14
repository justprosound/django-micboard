"""Telemetry and time-series data models.

Stores historical device metrics including battery trends, signal quality,
uptime statistics, and performance data. Used for analytics and reporting.
"""

from .health import APIHealthLog
from .sessions import WirelessUnitSample, WirelessUnitSession

__all__ = [
    "APIHealthLog",
    "WirelessUnitSample",
    "WirelessUnitSession",
]
