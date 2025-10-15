# Changelog

All notable changes to django-micboard are documented here.

**Version format:** CalVer (YY.MM.DD)

**Status:** Active development, not production-ready

---

## [25.10.15] - 2025-10-15

### Changed
- Updated version to use CalVer (YY.MM.DD) format
- Removed ownership claims from codebase
- Updated to FOSS community contribution model
- Simplified README for development-only status
- Removed PyPI packaging documentation (never released)
- Updated documentation to reflect active development status

---

## [25.10.14] - 2025-10-14

### Features

**Core Functionality**
- Real-time Shure wireless microphone monitoring via Django web interface
- Shure System API integration with automatic retry and exponential backoff
- WebSocket broadcasting via Django Channels for live updates
- Background polling service for continuous device monitoring (`poll_devices` management command)
- User assignment and alert notification system
- Rate-limited REST API endpoints

**Supported Devices**
- UHF-R, QLX-D, ULX-D, Axient Digital, PSM1000

**Architecture**
- Middleware-based: Shure System API (external) → Django app → WebSocket clients
- Django 4.2+ and Django 5.0+ compatible
- Python 3.9+ compatible
- Async WebSocket support via Django Channels 4.0+

**Models & Data**
- Receiver, Channel, Transmitter models for device tracking
- Location and MonitoringGroup models for organization
- DeviceAssignment model for user-to-device associations
- Alert and UserAlertPreference models for notifications
- Custom model managers for common query patterns

**API Features**
- Rate limiting with token bucket algorithm (Django cache-based)
- Automatic retry with exponential backoff (0.5s, 1s, 2s)
- Health tracking for Shure System API connection
- Configurable timeouts and SSL verification
- Connection pooling via requests.Session

**API Endpoints**
- `/api/data/` - Get all device data (rate limited: 120 req/min)
- `/api/receivers/` - List all receivers
- `/api/receivers/{id}/` - Get receiver details
- `/api/discover/` - Discover new devices (rate limited: 5 req/min)
- `/api/refresh/` - Force refresh (rate limited: 10 req/min)
- `/api/health/` - Check API health status
- `/api/config/` - Get/update configuration
- `/api/groups/{id}/` - Update group settings

**WebSocket**
- Real-time device updates via `ws://server/ws/micboard/`
- Automatic reconnection
- Message types: device_update, alert, status

**Admin Interface**
- Full Django admin for all models
- Advanced filtering and search
- Custom displays with relationship counts
- Inline editing capabilities

**Rate Limiting**
- Client-side: Prevents overwhelming Shure System API
- Server-side: Protects app from client abuse
- Per-IP tracking with sliding window algorithm
- Returns HTTP 429 with Retry-After header

**User Assignment System**
- Fine-grained device-to-user assignments
- Priority levels: low, normal, high, critical
- Per-device alert preferences
- Quiet hours support
- Team-based monitoring groups
- Alert history tracking

### Requirements

- Python 3.9+
- Django 4.2+ or 5.0+
- Shure System API server (external, installed separately)
- Redis (recommended for production WebSocket support)

### Known Limitations

- Requires external Shure System API server
- WebSocket subscriptions require manual implementation
- No historical data retention (current state only)
- Development-stage error handling

---

## Previous Development

This project is a complete refactoring of the original Tornado-based micboard into a modern Django application. No prior versions were released.
