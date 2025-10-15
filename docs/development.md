# Developer Guide

Guide for developers contributing to or extending Django Micboard.

## Development Setup

### Requirements

- Python 3.9+
- Django 4.2+ or 5.0+
- Poetry or pip for dependency management
- Git

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

3. Install development dependencies:
```bash
pip install -r dev-requirements.txt
```

4. Run tests:
```bash
pytest tests/ -v
```

### Project Structure

```
django-micboard/
├── micboard/                # Main package
│   ├── admin/              # Django admin interfaces
│   │   ├── assignments.py  # Assignment/alert admins
│   │   ├── devices.py      # Device admins
│   │   └── monitoring.py   # Monitoring/config admins
│   ├── models/             # Django models
│   │   ├── assignments.py  # User assignments & alerts
│   │   ├── devices.py      # Receivers, channels, transmitters
│   │   └── locations.py    # Locations & monitoring groups
│   ├── shure/              # Shure API integration
│   │   ├── client.py       # HTTP client with pooling
│   │   ├── transformers.py # Data transformers
│   │   └── websocket.py    # WebSocket handling
│   ├── views/              # Django views
│   │   ├── api.py          # REST API endpoints
│   │   └── dashboard.py    # Dashboard views
│   ├── management/commands/ # Management commands
│   ├── static/             # Static assets
│   ├── templates/          # Django templates
│   ├── consumers.py        # WebSocket consumers
│   ├── decorators.py       # View decorators
│   ├── routing.py          # WebSocket routing
│   ├── serializers.py      # Data serializers
│   ├── signals.py          # Django signals
│   └── urls.py             # URL configuration
├── tests/                  # Test suite
│   ├── test_models.py      # Model tests
│   └── test_package_structure.py  # PyPI validation
├── docs/                   # Documentation
└── pyproject.toml          # Package configuration
```

## Code Organization

### Package Split Rationale

The codebase has been organized into focused modules for maintainability:

#### Shure Package (`micboard/shure/`)

**Purpose:** Isolate all Shure System API interaction logic.

- **client.py** (394 lines)
  - HTTP client with connection pooling
  - Automatic retry with exponential backoff
  - Health tracking and error handling
  - Thread-safe operations

- **transformers.py** (286 lines)
  - Transform Shure API responses → micboard format
  - Channel status computation
  - Battery health analysis
  - Signal quality calculations

- **websocket.py** (136 lines)
  - Real-time WebSocket connections to Shure devices
  - Automatic reconnection
  - Message parsing and routing

#### Admin Package (`micboard/admin/`)

**Purpose:** Organize Django admin by functional area.

- **devices.py** (189 lines)
  - ReceiverAdmin, ChannelAdmin, TransmitterAdmin
  - List displays, filters, search
  - Read-only fields for API-sourced data

- **assignments.py** (100 lines)
  - DeviceAssignmentAdmin, AlertAdmin
  - User assignment management
  - Alert preferences

- **monitoring.py** (57 lines)
  - LocationAdmin, MonitoringGroupAdmin
  - Configuration admin
  - Group management

#### Serializers Module (`micboard/serializers.py`)

**Purpose:** DRY principle for data serialization.

- 8 reusable functions with keyword-only parameters
- Eliminates ~100 lines of duplicate code
- Consistent serialization across views and commands

### Django Best Practices

#### Keyword-Only Parameters

All functions use keyword-only parameters for clarity:

```python
def serialize_receiver_detail(receiver, *, include_extra=False):
    """
    Serialize receiver with keyword-only parameters.

    Args:
        receiver: Receiver instance
        include_extra: Whether to include computed properties (keyword-only)
    """
    pass
```

Benefits:
- Prevents boolean confusion: `func(receiver, True)` vs `func(receiver, include_extra=True)`
- Self-documenting code
- Easier to extend without breaking compatibility

#### Type Hints

Modern type hints with `__future__` annotations:

```python
from __future__ import annotations

from typing import Optional, Dict, List
from django.db.models import QuerySet

def process_devices(
    receivers: QuerySet[Receiver],
    *,
    include_offline: bool = False
) -> List[Dict[str, Any]]:
    """Process receivers with full type annotations."""
    pass
```

#### Model Managers

Custom managers for common queries:

```python
class ReceiverManager(models.Manager):
    def active(self) -> QuerySet[Receiver]:
        """Return active receivers."""
        return self.filter(is_active=True)

    def online_recently(self, *, minutes: int = 30) -> QuerySet[Receiver]:
        """Return receivers seen in last N minutes."""
        threshold = timezone.now() - timedelta(minutes=minutes)
        return self.filter(last_seen__gte=threshold)
```

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_models.py -v

# Specific test
pytest tests/test_models.py::TestReceiver::test_mark_online -v

# With coverage
pytest tests/ --cov=micboard --cov-report=html
```

### Test Structure

#### Model Tests (`test_models.py`)

38 tests covering all models:
- Receiver online/offline tracking
- Channel-Transmitter relationships
- DeviceAssignment validation
- Alert creation and preferences
- Location and MonitoringGroup hierarchies

#### Package Structure Tests (`test_package_structure.py`)

22 tests validating PyPI standards:
- No deprecated Django APIs
- Proper app configuration
- Model naming conventions
- Docstring coverage
- Import structure

### Writing Tests

Follow these conventions:

```python
import pytest
from django.test import TestCase
from micboard.models import Receiver

class TestReceiver(TestCase):
    """Test Receiver model."""

    def setUp(self):
        """Set up test fixtures."""
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            ip="192.168.1.100",
            device_type="ulxd"
        )

    def test_mark_online(self):
        """Test marking receiver online."""
        self.receiver.mark_online()
        self.assertTrue(self.receiver.is_active)
        self.assertIsNotNone(self.receiver.last_seen)
```

## Code Quality

### Style Guide

- PEP 8 compliant
- Type hints required for public functions
- Docstrings required for all modules, classes, and public functions
- Keyword-only parameters for boolean/optional arguments

### Linting

```bash
# Run ruff for linting
ruff check micboard/

# Auto-fix issues
ruff check --fix micboard/

# Format code
ruff format micboard/
```

### Type Checking

```bash
# Run mypy
mypy micboard/
```

## Django Compatibility

### Supported Versions

- Django 4.2 LTS
- Django 5.0+
- Python 3.9+

### No Backwards Compatibility

This package targets modern Django and Python versions only. We do not maintain backwards compatibility with:
- Django < 4.2
- Python < 3.9
- Deprecated Django APIs

### Migration Strategy

When Django deprecates APIs:
1. Update to new API immediately
2. No transitional compatibility layers
3. Bump minimum Django version requirement

## Shure API Integration

### Client Architecture

The Shure System API client uses:
- `requests.Session` for connection pooling
- `urllib3.Retry` for automatic retries
- Exponential backoff (0.5s, 1s, 2s)
- Health tracking (consecutive failures)

### Adding New Device Types

1. Add device type to `DEVICE_TYPE_CHOICES` in models:
```python
DEVICE_TYPE_CHOICES = [
    ('ulxd', 'ULX-D'),
    ('qlxd', 'QLX-D'),
    ('axient', 'Axient Digital'),
    ('new_type', 'New Type'),  # Add here
]
```

2. Add transformer logic in `shure/transformers.py`:
```python
def transform_new_type(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform new device type data."""
    pass
```

3. Update client in `shure/client.py` to handle new endpoints

### WebSocket Integration

For real-time updates from Shure devices:

```python
from micboard.shure import ShureWebSocketClient

client = ShureWebSocketClient(ip='192.168.1.100')
client.connect()
client.subscribe_to_updates(callback=handle_update)
```

## Deployment

### PyPI Package

Build and publish:

```bash
# Build package
python -m build

# Check package
twine check dist/*

# Upload to PyPI
twine upload dist/*
```

### Documentation

Build documentation:

```bash
# Using MkDocs
mkdocs build

# Serve locally
mkdocs serve
```

Deploy to Read the Docs:
1. Connect GitHub repository
2. Configure `.readthedocs.yaml`
3. Documentation auto-builds on push

## Contributing

### Workflow

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Make changes with tests
4. Run test suite: `pytest tests/`
5. Commit with clear messages
6. Push and create pull request

### Commit Messages

Follow conventional commits:

```
feat: Add support for Axient Digital receivers
fix: Correct battery percentage calculation
docs: Update API reference
test: Add tests for device discovery
refactor: Split shure_api_client into package
chore: Update dependencies
```

### Pull Request Guidelines

- Include tests for new features
- Update documentation
- Ensure all tests pass
- Follow code style guidelines
- Keep changes focused and atomic

## Getting Help

- GitHub Issues: https://github.com/justprosound/django-micboard/issues
- Documentation: https://django-micboard.readthedocs.io
- Community Discussions: Open an issue on GitHub

## License

AGPL-3.0-or-later - see LICENSE file for details.
