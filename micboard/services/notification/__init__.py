"""Notification and broadcasting services for django-micboard.

This package contains services for:
- Real-time broadcasting via WebSocket/SSE
- Event emission and signal management
- Email notifications
"""

from __future__ import annotations

from .broadcast_service import BroadcastService
from .email import EmailService
from .signal_emitter import SignalEmitter

__all__ = [
    "BroadcastService",
    "EmailService",
    "SignalEmitter",
]
