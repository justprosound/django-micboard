# Django Micboard - AI Agent Instructions

## Project Overview
Open source Django app for real-time multi-manufacturer wireless microphone monitoring. Integrates with manufacturer APIs (Shure, Sennheiser, etc.) for device communication.

**Status:** Active development, not production-ready
**Target:** Django 4.2+/5.0+, Python 3.9+
**Version:** CalVer (YY.MM.DD) - Current: 25.10.17
**License:** AGPL-3.0-or-later

## Architecture

### Data Flow
```
Manufacturer APIs → ManufacturerPlugin → poll_devices → Models → WebSocket
```

- **Manufacturer APIs**: External APIs for device communication (Shure System API, etc.)
- **ManufacturerPlugin**: Plugin interface for manufacturer-specific implementations
- **poll_devices**: Management command that polls APIs, updates models, broadcasts via Channels
- **WebSocket**: Real-time updates to frontend via Django Channels

### Package Structure
```
micboard/
├── manufacturers/          # Plugin architecture for multi-manufacturer support
│   ├── __init__.py         # Plugin registration and discovery
│   ├── shure/              # Shure-specific implementation
│   └── sennheiser/         # Sennheiser-specific implementation
├── admin/                  # Django admin interfaces
├── models/                 # Django models (manufacturers, devices, assignments, locations)
├── views/                  # REST API and dashboard views
├── serializers.py          # Centralized serialization
└── decorators.py           # Rate limiting decorators
```

## Key Patterns

### 1. Plugin Architecture
Use manufacturer plugins for extensibility:

```python
from micboard.manufacturers import get_manufacturer_plugin

# Get plugin for a manufacturer
plugin = get_manufacturer_plugin(manufacturer.code)
devices = plugin.get_devices()
```

### 2. Serialization (DRY Principle)
Always use `serializers.py` functions:

```python
from micboard.serializers import serialize_receivers
data = serialize_receivers(include_extra=True)  # Keyword-only params
```

### 3. Keyword-Only Parameters
Use `*` for optional/boolean parameters:

```python
def serialize_receiver(receiver, *, include_extra=False):
    pass
```

### 4. Rate Limiting
All API views must be rate-limited:

```python
from micboard.decorators import rate_limit_view

@rate_limit_view(max_requests=120, window_seconds=60)
def data_view(request):
    return JsonResponse(data)
```

### 5. Custom Model Managers
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

### Adding New Manufacturers
1. Create plugin class inheriting from `ManufacturerPlugin`
2. Implement required methods (`get_devices`, `transform_device_data`, etc.)
3. Register in `manufacturers/__init__.py`
4. Configure manufacturer in database

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
4. Never communicate with devices directly - use manufacturer APIs
5. All public API endpoints need rate limiting
6. Missing docstrings fail tests
7. Manufacturer data must be isolated by manufacturer relationships

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
- **Plugins**: `micboard/manufacturers/__init__.py`
- **Models**: `micboard/models/devices.py` (custom managers)
- **Architecture**: `docs/architecture.md`
- **API Reference**: `docs/api-reference.md`
