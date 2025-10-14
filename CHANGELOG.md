# Micboard Changelog

## 2.2.0 - Rate Limiting, Retry Logic, and PyPI Packaging (Current)

### Added
- **Python package distribution**:
  - `setup.py` for legacy compatibility
  - `pyproject.toml` for modern packaging (PEP 517/518)
  - `MANIFEST.in` for file inclusion
  - `.gitignore` for development
  - `LICENSE` file (MIT)
  - `PACKAGING.md` with comprehensive distribution guide
- **GitHub Actions workflow** for automated PyPI publishing
- **Package metadata** in `__init__.py` (`__version__`, `__author__`, `__license__`)
- **Test script** (`test_package.sh`) to verify package building

### Distribution
- **PyPI**: `pip install django-micboard`
- **GitHub**: `pip install git+https://github.com/...`
- **Source**: `pip install -e .`
- **Optional dependencies**: `[redis]` for production, `[dev]` for development tools

### Rate Limiting & Retry
- **Rate limiting for API client**: Decorator-based rate limiting for Shure System API calls
  - Configurable requests per second for each method
  - Token bucket algorithm using Django cache
  - Prevents overwhelming the Shure System API server
- **Automatic retry with exponential backoff**: 
  - Configurable max retries (default: 3)
  - Exponential backoff between retries (default: 0.5s base)
  - Retry on specific HTTP status codes (429, 500, 502, 503, 504)
  - Uses urllib3 Retry with requests HTTPAdapter
- **Rate limiting for micboard API endpoints**:
  - `/api/data/`: 120 requests/minute (2 req/sec)
  - `/api/discover/`: 5 requests/minute (expensive operation)
  - `/api/refresh/`: 10 requests/minute
  - Sliding window algorithm with per-IP tracking
  - Returns HTTP 429 with `Retry-After` header
- **Rate limiting decorators**: `rate_limit_view` and `rate_limit_user` in `decorators.py`
- Configuration options in `MICBOARD_CONFIG`:
  - `SHURE_API_MAX_RETRIES`
  - `SHURE_API_RETRY_BACKOFF`
  - `SHURE_API_RETRY_STATUS_CODES`

### Changed
- `ShureSystemAPIClient` now uses requests Session with retry strategy
- All public API methods decorated with `@rate_limit` for client-side limiting
- Requirements updated to include `urllib3>=2.0.0`

### Technical Details
- **Client-side rate limiting**: Prevents micboard from overwhelming Shure API
- **Server-side rate limiting**: Protects micboard from client abuse
- **Graceful degradation**: Failed requests log errors but don't crash
- **Caching integration**: Rate limit state stored in Django cache

## 2.1.0 - User Assignment & Monitoring System

### Added
- **Location Model**: Link devices to buildings/rooms with GenericForeignKey support for external location models
- **MonitoringGroup Model**: Team-based device monitoring with many-to-many relationships
- **DeviceAssignment Model**: Fine-grained user-to-device assignments with per-device alert preferences
- **UserAlertPreference Model**: Global alert preferences per user (notification methods, battery thresholds, quiet hours)
- **Alert Model**: Alert history tracking with status management (pending, sent, acknowledged, resolved)
- New admin interfaces for all monitoring models with:
  - Advanced filtering and search
  - Custom displays showing counts and relationships
  - Inline editing capabilities
  - Automatic timestamp tracking
- `USER_ASSIGNMENT.md`: Comprehensive documentation for the assignment system

### Changed
- Device model now includes helper methods: `get_assigned_users()`, `get_monitoring_groups()`
- Admin displays enhanced with relationship counts and better organization

### Features
- **Scale to hundreds of devices**: Efficient queries with proper indexing
- **Flexible location integration**: Works with or without external location models
- **Customizable alerts**: Per-user and per-device alert preferences
- **Team collaboration**: Monitoring groups for organizing users
- **Alert rate limiting**: Prevent alert spam with configurable intervals
- **Quiet hours**: Disable alerts during specified time periods
- **Audit trail**: Complete alert history with device state snapshots
- **Priority-based assignments**: Low, normal, high, and critical priority levels

## 2.0.0 - Django Refactoring with Shure System API

### Major Changes
- **Complete Django 4.2 Refactoring**: Converted from Tornado-based architecture to Django
- **Shure System API Integration**: Replaced direct device communication with official Shure System API middleware
- **Async WebSocket Support**: Implemented using Django Channels 4.0+ with AsyncWebsocketConsumer
- **Real-time Updates**: Background polling service broadcasts device status via WebSocket channels

### Added
- `shure_api_client.py`: ShureSystemAPIClient class for all API communication
- `management/commands/poll_devices.py`: Background polling service with configurable intervals
- `consumers.py`: Async WebSocket consumer for real-time client updates
- Enhanced models with API integration fields:
  - Device: `api_device_id`, `last_seen`
  - Transmitter: `slot`, `updated_at`
- New API endpoints:
  - `/api/discover/`: Discover new Shure devices
  - `/api/refresh/`: Force refresh device data
- Configuration templates:
  - `settings_template.py`: Complete Django settings example
  - `QUICKSTART.md`: Step-by-step installation guide
  - `ARCHITECTURE.md`: System architecture documentation
- Production-ready features:
  - Redis caching for API responses
  - Channel layers for WebSocket broadcasting
  - systemd service configuration examples
  - Comprehensive logging

### Removed (Legacy Tornado Code)
- `py/` directory with all Tornado server code:
  - `tornado_server.py`
  - `channel.py`, `config.py`, `device_config.py`
  - `discover.py`, `iem.py`, `micboard.py`, `mic.py`
  - `networkdevice.py`, `offline.py`, `shure.py`, `util.py`
- Root-level legacy files:
  - `shure.py` (direct device communication)
  - `networkdevice.py` (network discovery)
  - `device_config.py` (device configuration)
  - `discover.py` (discovery logic)
- `views.SlotHandler`: Unused placeholder handler

### Changed
- **Architecture**: Middleware-based (Shure System API) vs direct device communication
- **Web Framework**: Django 4.2 instead of Tornado
- **WebSocket**: Django Channels instead of Tornado WebSocket
- **Database**: Django ORM instead of custom config files
- **Admin Interface**: Full Django admin for all models
- Views now use caching and proper error handling
- Admin displays show new API integration fields

### Dependencies
- Django >= 4.2
- channels >= 4.0.0
- daphne >= 4.0.0
- channels-redis >= 4.0.0
- requests >= 2.31.0
- asgiref >= 3.7.0
- redis >= 5.0.0

### Notes
- **No backwards compatibility**: This is a complete rewrite
- **Never deployed**: Previous version was never used in production
- Frontend static files and templates remain unchanged
- Requires separate Shure System API server installation
