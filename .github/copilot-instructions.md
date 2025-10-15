# Django Micboard - AI Agent Instructions

## Project Overview
Open source Django app for real-time Shure wireless microphone monitoring. Integrates with external Shure System API middleware for device communication.

**Status:** Active development, not production-ready
**Target:** Django 4.2+/5.0+, Python 3.9+
**Version:** CalVer (YY.MM.DD) - Current: 25.10.15
**License:** AGPL-3.0-or-later

## Architecture

### Data Flow
```
Shure Devices → Shure System API (external) → ShureSystemAPIClient → poll_devices → Models → WebSocket
```

- **Shure System API**: External middleware handling device communication
- **ShureSystemAPIClient**: HTTP client in `micboard/shure/client.py`
- **poll_devices**: Management command that polls API, updates models, broadcasts via Channels
- **WebSocket**: Real-time updates to frontend via Django Channels

### Package Structure
```
micboard/
├── shure/          # Shure API integration
├── admin/          # Django admin interfaces
├── models/         # Django models (devices, assignments, locations)
├── views/          # REST API and dashboard views
└── serializers.py  # Centralized serialization
```

## Key Patterns

### 1. Serialization (DRY Principle)
Always use `serializers.py` functions:

```python
from micboard.serializers import serialize_receivers
data = serialize_receivers(include_extra=True)  # Keyword-only params
```

### 2. Keyword-Only Parameters
Use `*` for optional/boolean parameters:

```python
def serialize_receiver(receiver, *, include_extra=False):
    pass
```

### 3. Rate Limiting
All API views must be rate-limited:

```python
from micboard.decorators import rate_limit_view

@rate_limit_view(max_requests=120, window_seconds=60)
def data_view(request):
    return JsonResponse(data)
```

### 4. Custom Model Managers
Use custom managers for common queries:

```python
receivers = Receiver.objects.active()
recent = Receiver.objects.online_recently(minutes=30)
```

## Development Workflows

### Running Tests
```bash
pytest tests/ -v  # 60 tests total
```

### Running Polling Service
```bash
python manage.py poll_devices  # Required for app to function
```

### Building Documentation
```bash
pip install -r docs/requirements.txt
mkdocs serve
```

## Code Quality

### Required
- Type hints with `from __future__ import annotations`
- Docstrings for all modules/classes/public functions
- Keyword-only parameters for optional args
- All tests must pass (`pytest tests/ -v`)

## Common Pitfalls

1. Don't bypass serializers - use `serializers.py` functions
2. Always use keyword-only params (`*`)
3. `poll_devices` must run for app to function
4. Never communicate with devices directly - use Shure System API
5. All public API endpoints need rate limiting
6. Missing docstrings fail tests

## Contributing

This is a community-driven open source project:
- No specific ownership claims
- Welcome contributions from anyone
- Follow existing code patterns and quality standards
- Run tests before submitting changes

## Key Files

- **Serializers**: `micboard/serializers.py` (8 reusable functions)
- **Rate Limiting**: `micboard/decorators.py`
- **Polling**: `micboard/management/commands/poll_devices.py`
- **Client**: `micboard/shure/client.py`
- **Architecture**: `docs/architecture.md`
- **API Reference**: `docs/api-reference.md`
