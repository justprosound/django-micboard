"""Business logic services for the micboard app.

This module provides high-level service APIs for:
- Device management (DeviceService)
- Network discovery (DiscoveryService)
- Polling orchestration (PollingService)
- Email notifications (EmailService)

Services encapsulate business logic and provide clean interfaces
for tasks, views, and management commands.
"""

from __future__ import annotations

# Core services
from .device_service import DeviceService, get_device_service
from .discovery_service_new import DiscoveryService
from .email import EmailService, email_service, send_alert_email, send_system_email
from .polling_service import PollingService, get_polling_service

__all__ = [
    # Device management
    "DeviceService",
    "get_device_service",
    # Discovery
    "DiscoveryService",
    # Polling
    "PollingService",
    "get_polling_service",
    # Email
    "EmailService",
    "email_service",
    "send_alert_email",
    "send_system_email",
]
