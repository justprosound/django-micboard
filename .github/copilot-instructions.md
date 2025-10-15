# Django Micboard - AI Agent Instructions

## Project Overview
Django reusable app for real-time Shure wireless microphone monitoring via **middleware architecture**: Shure System API (separate server) ↔ This Django app ↔ WebSocket clients. Never released, so **no backwards compatibility needed** - always use modern Django/Python APIs.

**Target:** Django 4.2+/5.0+, Python 3.9+. PyPI distribution ready.

## Critical Architecture Patterns

### 1. Middleware Data Flow (Most Important!)
```
Shure Devices → Shure System API (external) → Our ShureSystemAPIClient → poll_devices command → Django Models → WebSocket broadcast
```

- **Shure System API** is EXTERNAL middleware (not part of this app) - handles all device communication
- **ShureSystemAPIClient** (`micboard/shure/client.py`) polls the API, never talks to devices directly
- **poll_devices** management command is the backbone - runs continuously, polls API, updates models, broadcasts via Channels
- Models store last-seen state; WebSocket provides real-time updates to frontend

### 2. Package Organization (Post-Refactoring)
```
micboard/
├── shure/              # Shure API integration (was monolithic shure_api_client.py)
│   ├── client.py       # HTTP client with pooling/retry (394 lines)
│   ├── transformers.py # Shure API → micboard format (286 lines)
│   └── websocket.py    # Real-time WS connections (136 lines)
├── admin/              # Django admin split by function (was monolithic admin.py)
│   ├── devices.py      # Receiver/Channel/Transmitter admins
│   ├── assignments.py  # DeviceAssignment/Alert admins
│   └── monitoring.py   # Location/MonitoringGroup/Config admins
├── models/             # Models organized by domain
│   ├── devices.py      # Receiver, Channel, Transmitter
│   ├── assignments.py  # DeviceAssignment, Alert, UserAlertPreference
│   └── locations.py    # Location, MonitoringGroup, Group
├── views/              # Views split by purpose
│   ├── api.py          # REST endpoints
│   └── dashboard.py    # Template views
└── serializers.py      # Centralized serialization (DRY principle)
```

**Why split?** Large files (664/310 lines) → focused modules for maintainability. Recent refactoring (Oct 2024).

### 3. Serialization Pattern (DRY Anti-Duplication)
**Always use `serializers.py` functions** - never write custom serialization in views/commands:

```python
from micboard.serializers import serialize_receiver_detail, serialize_receivers

# ✅ CORRECT - Use centralized serializers
data = serialize_receivers(include_extra=True)  # Keyword-only params!

# ❌ WRONG - Don't duplicate serialization logic
data = {"name": receiver.name, "ip": receiver.ip, ...}  # Maintainability nightmare
```

**8 serializer functions:** `serialize_transmitter`, `serialize_channel`, `serialize_receiver`, `serialize_receivers`, `serialize_discovered_device`, `serialize_group`, `serialize_receiver_summary`, `serialize_receiver_detail`

### 4. Keyword-Only Parameters (Project Convention)
**All functions with boolean/optional parameters use `*` for keyword-only args:**

```python
# ✅ CORRECT - Prevents boolean confusion
def serialize_receiver(receiver, *, include_extra=False):  # Note the *
    pass

serialize_receiver(rx, include_extra=True)  # Self-documenting

# ❌ WRONG - Legacy style banned
def serialize_receiver(receiver, include_extra=False):  # Missing *
    pass

serialize_receiver(rx, True)  # What does True mean?
```

**Why:** Self-documenting code, prevents `func(obj, True, False)` confusion. Applied across all new code.

## Development Workflows

### Running Tests (60 total: 38 model + 22 PyPI validation)
```bash
# All tests
pytest tests/ -v

# Model tests only
pytest tests/test_models.py -v

# PyPI structure validation
pytest tests/test_package_structure.py -v

# With coverage
pytest tests/ --cov=micboard --cov-report=html
```

**Test organization:**
- `test_models.py`: 38 tests - Receiver online/offline, Channel-Transmitter relationships, DeviceAssignment validation
- `test_package_structure.py`: 22 tests - Validates PyPI Django reusable app standards (no deprecated APIs, proper imports, docstrings, model conventions)

### Local Development Setup
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r dev-requirements.txt
pytest tests/ -v  # Ensure all passing
```

### Running the Polling Service (Core of App)
```bash
# Standard operation (polls + broadcasts)
python manage.py poll_devices

# Poll once without WebSocket (testing)
python manage.py poll_devices --initial-poll-only

# Poll without broadcasting (background tasks)
python manage.py poll_devices --no-broadcast
```

**Critical:** This command MUST run for app to function - it's the data pipeline.

### Documentation Building (MkDocs + Read the Docs)
```bash
# Install docs dependencies
pip install -r docs/requirements.txt

# Serve locally
mkdocs serve  # Visit http://127.0.0.1:8000

# Build static site
mkdocs build  # Output to site/
```

**Docs structure:** `docs/` folder with `index.md`, `api-reference.md`, `development.md`, etc. Material theme. Auto-deploys via `.readthedocs.yaml`.

## Code Quality Standards

### Type Hints (Required)
```python
from __future__ import annotations  # Always first import
from typing import Optional, Dict, List

def process_devices(
    receivers: QuerySet[Receiver],
    *,
    include_offline: bool = False
) -> List[Dict[str, Any]]:
    """Full type annotations required."""
    pass
```

### Docstrings (Required for All Modules/Classes/Public Functions)
```python
"""
Module-level docstring explaining purpose.
"""

class Receiver(models.Model):
    """Represents a physical Shure wireless receiver unit."""
    
    def mark_online(self):
        """Mark receiver as active and update last_seen timestamp."""
        pass
```

**Why:** PyPI validation tests enforce this. Test failure if missing.

### Model Managers (Use Custom Querysets)
```python
# ✅ CORRECT - Semantic queries via custom managers
receivers = Receiver.objects.active()  # Custom manager method
recent = Receiver.objects.online_recently(minutes=30)
by_type = Receiver.objects.by_type("ulxd")

# ❌ AVOID - Raw filters scattered everywhere
receivers = Receiver.objects.filter(is_active=True)  # Duplicates logic
```

**Pattern:** Every model with common queries has custom manager/queryset. See `models/devices.py` for examples.

## Critical Integration Points

### Rate Limiting (Token Bucket via Django Cache)
**All API views must be rate-limited** using `@rate_limit_view` decorator:

```python
from micboard.decorators import rate_limit_view

@rate_limit_view(max_requests=120, window_seconds=60)  # 2 req/sec
def data_view(request):
    return JsonResponse(data)

# For authenticated users
from micboard.decorators import rate_limit_user
@rate_limit_user(max_requests=100, window_seconds=60)
def user_view(request):
    pass
```

**Standard limits:**
- `/api/data/`: 120/min (2 req/sec)
- `/api/discover/`: 5/min (expensive)
- `/api/refresh/`: 10/min
- Default: 60/min

**Implementation:** Sliding window algorithm, Django cache-based. Returns HTTP 429 with `Retry-After` header. See `decorators.py`.

### WebSocket Communication (Django Channels)
**Group name:** `micboard_updates` (hardcoded convention)

```python
# Broadcasting from management command
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    "micboard_updates",
    {"type": "device_update", "data": serialized_data}
)
```

**Consumer:** `micboard/consumers.py` handles WebSocket connections. **Routing:** `micboard/routing.py` defines WS URL patterns.

### Shure API Client Usage
```python
from micboard.shure import ShureSystemAPIClient, ShureAPIError

client = ShureSystemAPIClient()  # Uses MICBOARD_CONFIG settings

try:
    devices = client.poll_all_devices()  # Returns transformed data
    health = client.check_health()
except ShureAPIError as e:
    logger.error(f"Shure API error: {e}")
```

**Features:**
- Connection pooling via `requests.Session`
- Auto-retry with exponential backoff (0.5s, 1s, 2s)
- Health tracking (consecutive failures)
- Thread-safe operations

## Configuration (Django Settings)

```python
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'http://localhost:8080',  # Shure System API server
    'SHURE_API_USERNAME': None,  # Optional auth
    'SHURE_API_PASSWORD': None,
    'SHURE_API_TIMEOUT': 10,
    'SHURE_API_VERIFY_SSL': True,
    'SHURE_API_MAX_RETRIES': 3,
    'SHURE_API_RETRY_BACKOFF': 0.5,
    'SHURE_API_RETRY_STATUS_CODES': [429, 500, 502, 503, 504],
    'TRANSMITTER_INACTIVITY_SECONDS': 10,
}
```

See `docs/configuration.md` for all options.

## Common Pitfalls

1. **Don't bypass serializers** - Use `serializers.py` functions, never duplicate logic
2. **Always use keyword-only params** - Add `*` before optional/boolean parameters
3. **poll_devices must run** - App won't update without this command running
4. **No direct device communication** - Always go through Shure System API, never try to talk to devices directly
5. **Forget rate limiting** - All public API endpoints need `@rate_limit_view`
6. **Missing docstrings** - PyPI validation tests will fail without module/class/function docstrings

## Key Files to Reference

- **Architecture:** `docs/architecture.md` - Full system diagram and data flow
- **API Reference:** `docs/api-reference.md` - All REST/WebSocket endpoints
- **Developer Guide:** `docs/development.md` - Contributing, testing, code quality
- **Serialization:** `micboard/serializers.py` - 8 reusable serializers (228 lines)
- **Rate Limiting:** `micboard/decorators.py` - `@rate_limit_view` decorator
- **Polling Logic:** `micboard/management/commands/poll_devices.py` - Core data pipeline
- **Shure Client:** `micboard/shure/client.py` - API client with pooling/retry

## Quick Reference: Adding New Features

### Adding New API Endpoint
1. Add view to `micboard/views/api.py`
2. Add rate limiting: `@rate_limit_view(max_requests=X, window_seconds=Y)`
3. Use serializers from `serializers.py` for responses
4. Add URL to `micboard/urls.py`
5. Document in `docs/api-reference.md`
6. Write tests in `tests/test_models.py` or new test file

### Adding New Model
1. Add to appropriate file in `micboard/models/` (devices/assignments/locations)
2. Add custom manager/queryset if common queries exist
3. Add docstring to model and methods
4. Add admin to appropriate file in `micboard/admin/`
5. Create migration: `python manage.py makemigrations micboard`
6. Add serializer function to `serializers.py` if needed for API
7. Update `micboard/models/__init__.py` exports
8. Write tests in `tests/test_models.py`

### Supporting New Shure Device Type
1. Add to `DEVICE_TYPES` in `micboard/models/devices.py`
2. Add transformer logic in `micboard/shure/transformers.py`
3. Update client in `micboard/shure/client.py` for new endpoints
4. Test with `poll_devices` command
5. Update documentation in `docs/`
